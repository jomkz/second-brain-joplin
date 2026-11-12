"""Tests for the write tool, joplin_create_note, driven through a FastMCP client.

The tool is registered only when SBJ_WRITE_NOTEBOOKS says where notes may go, it
can only add a note to one of those notebooks, and it never tells a caller about
a notebook the filter hides.
"""

import asyncio
import json
import logging
import re
from collections.abc import Iterator
from typing import Any

import pytest
import respx
from fakes import FakeJoplin
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from second_brain_joplin import cli
from second_brain_joplin.errors import NOTEBOOK_FILTER_MESSAGE
from second_brain_joplin.models import MAX_NOTE_CHARS, MAX_TITLE_CHARS
from second_brain_joplin.server import create_server, mcp
from second_brain_joplin.tools.write import WRITES_OFF_MESSAGE

HEX_ID = re.compile(r"[0-9a-f]{32}")


class Vault:
    """Inbox, Work ─ Projects, and Journal; one note already in Work."""

    def __init__(self, joplin: FakeJoplin) -> None:
        self.joplin = joplin
        self.inbox = joplin.notebook("Inbox")
        self.work = joplin.notebook("Work")
        self.projects = joplin.notebook("Projects", parent=self.work)
        self.journal = joplin.notebook("Journal")
        self.existing = joplin.note("Existing", "already here", self.work)


@pytest.fixture
def joplin() -> Iterator[FakeJoplin]:
    with respx.mock:
        fake = FakeJoplin()
        fake.install()
        yield fake


@pytest.fixture
def vault(joplin: FakeJoplin) -> Vault:
    return Vault(joplin)


@pytest.fixture(autouse=True)
def _no_notebook_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SBJ_NOTEBOOKS", "SBJ_EXCLUDE_NOTEBOOKS", "SBJ_WRITE_NOTEBOOKS"):
        monkeypatch.delenv(name, raising=False)


def _server() -> FastMCP:
    """A server with the write tool registered, as SBJ_WRITE_NOTEBOOKS would make it."""
    return create_server(writes=True)


async def _create(**args: Any) -> dict[str, Any]:
    args = {"title": "Call with Sam", "body": "## Decisions\n- ship it", **args}
    async with Client(_server()) as client:
        result = await client.call_tool("joplin_create_note", args)
    content: dict[str, Any] = result.structured_content
    return content


async def _refused(**args: Any) -> str:
    args = {"title": "Call with Sam", "body": "## Decisions\n- ship it", **args}
    async with Client(_server()) as client:
        with pytest.raises(ToolError) as raised:
            await client.call_tool("joplin_create_note", args)
    return str(raised.value)


# -- whether the tool exists at all ---------------------------------------------


async def _tool_names(server: FastMCP) -> set[str]:
    async with Client(server) as client:
        return {tool.name for tool in await client.list_tools()}


async def test_a_server_is_read_only_until_write_notebooks_are_listed() -> None:
    assert "joplin_create_note" not in await _tool_names(mcp)
    assert "joplin_create_note" not in await _tool_names(create_server())


async def test_listing_write_notebooks_registers_the_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    assert "joplin_create_note" in await _tool_names(create_server())
    # An explicit choice wins over the environment.
    assert "joplin_create_note" not in await _tool_names(create_server(writes=False))


async def test_the_tool_declares_what_it_does_and_asks_for_a_prompt_every_time() -> None:
    async with Client(_server()) as client:
        tool = next(t for t in await client.list_tools() if t.name == "joplin_create_note")
    hints = tool.annotations
    assert hints is not None
    assert hints.read_only_hint is False
    assert hints.destructive_hint is False  # it only ever adds a note
    assert hints.idempotent_hint is False  # twice makes two notes
    assert hints.open_world_hint is False
    assert tool.meta is not None
    assert tool.meta["anthropic/requiresUserInteraction"] is True
    assert set(tool.input_schema["required"]) == {"title", "body", "notebook"}


@pytest.mark.parametrize("transport_args", [[], ["--transport", "http", "--no-auth"]])
def test_serve_registers_the_tool_from_an_env_file(
    transport_args: list[str], tmp_path: Any, joplin: FakeJoplin, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The server is built after the env file is read, so the file can turn writes on."""
    joplin.notebook("Inbox")
    env_file = tmp_path / "serve.env"
    env_file.write_text("SBJ_WRITE_NOTEBOOKS=Inbox\n")
    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: False)
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "")
    monkeypatch.delenv("SBJ_WRITE_NOTEBOOKS")  # so monkeypatch removes it again afterwards
    built: list[FastMCP] = []
    monkeypatch.setattr(FastMCP, "run", lambda self, *a, **k: built.append(self))
    monkeypatch.setattr(cli, "run_http", lambda server, options: built.append(server))

    cli.main(["serve", "--env-file", str(env_file), *transport_args])

    assert len(built) == 1
    assert "joplin_create_note" in asyncio.run(_tool_names(built[0]))


def test_serve_without_the_setting_builds_a_read_only_server(
    joplin: FakeJoplin, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: False)
    built: list[FastMCP] = []
    monkeypatch.setattr(FastMCP, "run", lambda self, *a, **k: built.append(self))
    cli.main(["serve"])
    assert "joplin_create_note" not in asyncio.run(_tool_names(built[0]))


# -- creating a note -------------------------------------------------------------


async def test_creates_the_note_in_the_notebook_named_by_title(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    result = await _create(notebook="Inbox")

    assert HEX_ID.fullmatch(result["id"])
    assert result["title"] == "Call with Sam"
    assert (result["notebook_id"], result["notebook"]) == (vault.inbox, "Inbox")
    assert result["created_time"].startswith("2023-11-14T")
    # Exactly one request wrote, and it said exactly this.
    assert vault.joplin.posts == [
        {
            "id": result["id"],
            "title": "Call with Sam",
            "body": "## Decisions\n- ship it",
            "parent_id": vault.inbox,
        }
    ]
    assert vault.joplin.notes[result["id"]]["parent_id"] == vault.inbox


async def test_the_new_note_reads_back_through_the_read_tool(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    async with Client(_server()) as client:
        created = (
            await client.call_tool(
                "joplin_create_note", {"title": "T", "body": "the body", "notebook": "Inbox"}
            )
        ).structured_content
        read = (
            await client.call_tool("joplin_read", {"note_id": created["id"]})
        ).structured_content
    assert (read["title"], read["body"], read["parent_id"]) == ("T", "the body", vault.inbox)


async def test_the_notebook_can_be_named_by_id(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    result = await _create(notebook=vault.inbox.upper())
    assert (result["notebook_id"], result["notebook"]) == (vault.inbox, "Inbox")


async def test_a_listed_notebook_covers_its_sub_notebooks(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", vault.work)
    result = await _create(notebook="Projects")
    assert result["notebook_id"] == vault.projects


async def test_a_star_allows_every_visible_notebook_and_no_hidden_one(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "*")
    monkeypatch.setenv("SBJ_EXCLUDE_NOTEBOOKS", "Journal")
    assert (await _create(notebook="Projects"))["notebook_id"] == vault.projects
    assert "can't be created in that notebook" in await _refused(notebook="Journal")
    assert "can't be created in that notebook" in await _refused(notebook=vault.journal)


async def test_an_empty_body_is_a_note_with_just_a_title(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    result = await _create(notebook="Inbox", body="")
    assert vault.joplin.notes[result["id"]]["body"] == ""


async def test_the_title_is_put_on_one_line_and_trimmed(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    result = await _create(notebook=" Inbox ", title="  Call\nwith\t Sam  ")
    assert result["title"] == "Call with Sam"
    assert vault.joplin.posts[0]["title"] == "Call with Sam"


async def test_it_never_touches_an_existing_note(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "*")
    before = dict(vault.joplin.notes[vault.existing])
    await _create(notebook="Work", title="Existing")  # the same title as a note there
    assert vault.joplin.notes[vault.existing] == before
    assert len(vault.joplin.notes) == 2
    # The only request that isn't a GET is the one POST.
    assert [r for r in vault.joplin.requests if r.startswith("POST")] == ["POST /notes"]


# -- notebooks a note can't go into ---------------------------------------------


async def test_every_notebook_that_cant_receive_a_note_is_refused_the_same_way(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    monkeypatch.setenv("SBJ_EXCLUDE_NOTEBOOKS", "Journal")
    answers = {
        "hidden, by title": await _refused(notebook="Journal"),
        "hidden, by id": await _refused(notebook=vault.journal),
        "visible but not listed, by title": await _refused(notebook="Work"),
        "visible but not listed, by id": await _refused(notebook=vault.work),
        "no such title": await _refused(notebook="Nowhere"),
        "no such id": await _refused(notebook="f" * 32),
    }
    expected = (
        "A note can't be created in that notebook. Notebooks that can receive notes: "
        f"'Inbox' ({vault.inbox})"
    )
    assert set(answers.values()) == {expected}  # nothing tells a hidden notebook apart
    assert vault.joplin.posts == []


async def test_a_title_two_writable_notebooks_share_needs_the_id(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    twin = vault.joplin.notebook("Inbox", parent=vault.work)
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", f"{vault.inbox},{twin}")
    message = await _refused(notebook="Inbox")
    assert vault.inbox in message and twin in message
    assert vault.joplin.posts == []
    assert (await _create(notebook=twin))["notebook_id"] == twin


async def test_a_refusal_names_at_most_twenty_notebooks(
    joplin: FakeJoplin, monkeypatch: pytest.MonkeyPatch
) -> None:
    for n in range(23):
        joplin.notebook(f"Notebook {n:02d}")
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "*")
    message = await _refused(notebook="Nowhere")
    assert "'Notebook 00'" in message and "'Notebook 19'" in message
    assert "'Notebook 20'" not in message
    assert message.endswith("; and 3 more")


@pytest.mark.parametrize(
    "args",
    [
        {"title": ""},
        {"title": "x" * (MAX_TITLE_CHARS + 1)},
        {"body": "x" * (MAX_NOTE_CHARS + 1)},
        {"notebook": ""},
        {"notebook": "x" * (MAX_TITLE_CHARS + 1)},
    ],
)
async def test_out_of_range_arguments_are_refused_before_joplin_is_called(
    args: dict[str, Any], vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    await _refused(**{"notebook": "Inbox", **args})
    assert vault.joplin.requests == []


async def test_a_title_of_only_spaces_is_refused_before_joplin_is_called(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    assert await _refused(notebook="Inbox", title=" \n\t ") == "A note needs a title."
    assert vault.joplin.requests == []


async def test_limits_at_the_ceiling_are_accepted(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    result = await _create(notebook="Inbox", title="t" * MAX_TITLE_CHARS, body="b" * MAX_NOTE_CHARS)
    assert len(vault.joplin.notes[result["id"]]["body"]) == MAX_NOTE_CHARS


# -- settings that are off or wrong ----------------------------------------------


async def test_without_the_setting_the_tool_refuses_even_if_it_is_registered(
    vault: Vault,
) -> None:
    assert await _refused(notebook="Inbox") == WRITES_OFF_MESSAGE
    assert vault.joplin.posts == []


@pytest.mark.parametrize(
    ("variable", "value", "detail"),
    [
        ("SBJ_WRITE_NOTEBOOKS", "Inbocks", "SBJ_WRITE_NOTEBOOKS: no notebook is titled 'Inbocks'"),
        ("SBJ_EXCLUDE_NOTEBOOKS", "Jurnal", "SBJ_EXCLUDE_NOTEBOOKS: no notebook is titled"),
    ],
)
async def test_settings_that_do_not_resolve_refuse_the_write(
    variable: str,
    value: str,
    detail: str,
    vault: Vault,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    monkeypatch.setenv(variable, value)
    assert await _refused(notebook="Inbox") == NOTEBOOK_FILTER_MESSAGE
    assert detail in caplog.text
    assert vault.joplin.posts == []


async def test_a_write_notebook_the_filter_hides_refuses_the_write(
    vault: Vault, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Journal")
    monkeypatch.setenv("SBJ_EXCLUDE_NOTEBOOKS", "Journal")
    assert await _refused(notebook="Journal") == NOTEBOOK_FILTER_MESSAGE
    assert "'Journal' is hidden by the notebook filter" in caplog.text
    assert vault.joplin.posts == []


async def test_a_wrong_write_list_does_not_stop_reads(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbocks")
    async with Client(_server()) as client:
        hits = (await client.call_tool("joplin_search", {"query": "already"})).structured_content
    assert [hit["id"] for hit in hits["result"]] == [vault.existing]
    # With no filter set, a read doesn't even ask for the notebook list.
    assert vault.joplin.count("/folders") == 0


# -- when Joplin fails ------------------------------------------------------------
#
# Three outcomes, and the tool must not confuse them: nothing was created (say why),
# the note was created (say so, even if Joplin's answer got lost), or it can't be
# known yet (say that, and make a repeat safe).


async def test_joplin_refusing_the_note_is_an_error_and_nothing_is_created(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    vault.joplin.post_status = 500
    message = await _refused(notebook="Inbox")
    assert "HTTP 500" in message
    assert "may or may not" not in message  # Joplin answered, and the note isn't there
    assert len(vault.joplin.notes) == 1


async def test_a_refused_connection_is_a_plain_failure_not_a_maybe(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    vault.joplin.post_refused = True  # the notebook list was read; the POST never left
    message = await _refused(notebook="Inbox")
    assert "unreachable" in message
    assert "may or may not" not in message
    assert vault.joplin.posts == []
    # Nothing was sent, so nothing is asked afterwards either.
    assert vault.joplin.requests[-1] == "POST /notes"


async def test_joplin_down_before_the_notebook_list_is_reported(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    vault.joplin.down = True
    assert "unreachable" in await _refused(notebook="Inbox")
    assert vault.joplin.requests == ["/folders"]  # it never got as far as writing


async def test_a_lost_answer_is_still_a_created_note_not_a_duplicate(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    vault.joplin.post_loses_response = True  # Joplin made the note; we saw a timeout

    result = await _create(notebook="Inbox")

    assert result["id"] == vault.joplin.posts[0]["id"]
    assert result["id"] in vault.joplin.notes
    assert len(vault.joplin.posts) == 1  # no second attempt
    assert result["created_time"] is None  # Joplin's answer, and with it the time, was lost
    assert result["already_created"] is False


async def test_an_error_answer_for_a_note_that_was_saved_is_still_a_created_note(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    vault.joplin.post_errors_after_saving = True
    result = await _create(notebook="Inbox")
    assert result["id"] in vault.joplin.notes


async def test_a_timeout_while_joplin_is_still_saving_is_a_maybe_and_a_repeat_is_safe(
    vault: Vault, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    vault.joplin.post_saves_late = True
    args = {"title": "Call with Sam", "body": "notes", "notebook": "Inbox"}

    async with Client(_server()) as client:
        with pytest.raises(ToolError) as raised:
            await client.call_tool("joplin_create_note", args)
        # Not there when the tool looked, so it must not claim the note failed.
        assert "may or may not have been created" in str(raised.value)
        assert "won't make a second copy" in str(raised.value)
        assert "note create unconfirmed" in caplog.text

        vault.joplin.land_late()  # Joplin finishes saving
        vault.joplin.post_saves_late = False
        again = (await client.call_tool("joplin_create_note", args)).structured_content

    assert again["already_created"] is True
    assert again["id"] == vault.joplin.posts[0]["id"]
    assert len(vault.joplin.posts) == 1  # the repeat found the note; it sent nothing
    assert len(vault.joplin.notes) == 2  # the one already in Work, and this one


async def test_a_maybe_that_never_landed_is_created_by_the_repeat(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    vault.joplin.post_saves_late = True
    args = {"title": "Call with Sam", "body": "notes", "notebook": "Inbox"}
    async with Client(_server()) as client:
        with pytest.raises(ToolError):
            await client.call_tool("joplin_create_note", args)
        vault.joplin.post_saves_late = False  # the first attempt is never saved
        again = (await client.call_tool("joplin_create_note", args)).structured_content
    assert again["already_created"] is False
    assert again["id"] == vault.joplin.posts[1]["id"] != vault.joplin.posts[0]["id"]
    assert again["id"] in vault.joplin.notes


async def test_when_joplin_stops_answering_after_the_post_it_is_a_maybe(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    vault.joplin.post_loses_response = True
    vault.joplin.down_after_post = True  # the answer is lost, and so is the follow-up
    message = await _refused(notebook="Inbox")
    assert "may or may not have been created" in message


async def test_an_error_answer_and_no_way_to_check_is_a_maybe(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    vault.joplin.post_errors_after_saving = True
    vault.joplin.down_after_post = True
    assert "may or may not have been created" in await _refused(notebook="Inbox")


async def test_a_rejected_token_is_reported_as_such(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    vault.joplin.post_status = 403
    assert "JOPLIN_API_TOKEN" in await _refused(notebook="Inbox")
    # No follow-up question to Joplin: it would be rejected the same way.
    assert vault.joplin.requests[-1] == "POST /notes"


async def test_an_id_of_joplins_own_is_the_one_reported(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    vault.joplin.post_ignores_id = True
    args = {"title": "T", "body": "B", "notebook": "Inbox"}
    async with Client(_server()) as client:
        result = (await client.call_tool("joplin_create_note", args)).structured_content
        again = (await client.call_tool("joplin_create_note", args)).structured_content
    assert result["id"] != vault.joplin.posts[0]["id"]
    assert result["id"] in vault.joplin.notes
    assert (again["id"], again["already_created"]) == (result["id"], True)  # found by that id


# -- the same request again -------------------------------------------------------


async def test_an_identical_request_soon_after_returns_the_same_note(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "*")
    args = {"title": "Call with Sam", "body": "notes", "notebook": "Inbox"}
    async with Client(_server()) as client:
        first = (await client.call_tool("joplin_create_note", args)).structured_content
        second = (await client.call_tool("joplin_create_note", args)).structured_content
        # Anything different is a different note: the text, the title, the notebook.
        others = [
            (await client.call_tool("joplin_create_note", {**args, **change})).structured_content
            for change in ({"body": "notes!"}, {"title": "Call with Sam 2"}, {"notebook": "Work"})
        ]

    assert (first["already_created"], second["already_created"]) == (False, True)
    assert second["id"] == first["id"]
    assert [other["already_created"] for other in others] == [False, False, False]
    assert len({first["id"], *(other["id"] for other in others)}) == 4
    assert len(vault.joplin.posts) == 4


async def test_a_repeat_after_the_note_was_deleted_creates_it_again(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    args = {"title": "Call with Sam", "body": "notes", "notebook": "Inbox"}
    async with Client(_server()) as client:
        first = (await client.call_tool("joplin_create_note", args)).structured_content
        del vault.joplin.notes[first["id"]]  # the user threw it away and asks again
        second = (await client.call_tool("joplin_create_note", args)).structured_content
    assert second["already_created"] is False
    assert second["id"] != first["id"] and second["id"] in vault.joplin.notes


async def test_a_repeat_that_cannot_check_the_earlier_note_does_not_make_another(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    args = {"title": "Call with Sam", "body": "notes", "notebook": "Inbox"}
    async with Client(_server()) as client:
        await client.call_tool("joplin_create_note", args)
        vault.joplin.note_status = 500  # Joplin can't say whether that note is still there
        with pytest.raises(ToolError, match="HTTP 500"):
            await client.call_tool("joplin_create_note", args)
    assert len(vault.joplin.posts) == 1  # better an error than a second copy


async def test_a_failed_request_is_not_remembered(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    args = {"title": "Call with Sam", "body": "notes", "notebook": "Inbox"}
    async with Client(_server()) as client:
        vault.joplin.post_status = 500
        with pytest.raises(ToolError):
            await client.call_tool("joplin_create_note", args)
        vault.joplin.post_status = None
        requests_before = len(vault.joplin.requests)
        result = (await client.call_tool("joplin_create_note", args)).structured_content
    assert result["already_created"] is False
    # Notebook list, then the POST: no look-up of an id that was never created.
    assert vault.joplin.requests[requests_before:] == ["/folders", "POST /notes"]


# -- the record it leaves --------------------------------------------------------


async def test_each_created_note_is_logged_by_id_with_no_content(
    vault: Vault, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="second_brain_joplin")
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    result = await _create(notebook="Inbox", title="Secret title", body="secret body text")
    for step in ("create sent", "created"):  # before the request goes out, and after
        line = f"note {step} id={result['id']} notebook={vault.inbox} caller=anonymous"
        assert line in caplog.text
    assert "tool=joplin_create_note caller=anonymous outcome=ok" in caplog.text
    assert "Secret title" not in caplog.text
    assert "secret body text" not in caplog.text


async def test_a_refusal_writes_no_note_line(
    vault: Vault, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="second_brain_joplin")
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    await _refused(notebook="Journal")
    assert "note create" not in caplog.text  # refused before anything was sent
    assert "outcome=error" in caplog.text


async def test_a_request_joplin_refuses_is_logged_as_sent_then_failed(
    vault: Vault, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="second_brain_joplin")
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    vault.joplin.post_status = 500
    await _refused(notebook="Inbox", title="Secret title")
    sent_id = vault.joplin.posts[0]["id"]
    assert f"note create sent id={sent_id}" in caplog.text
    assert f"note create failed id={sent_id}" in caplog.text
    assert "note created" not in caplog.text
    assert "Secret title" not in caplog.text


async def test_the_result_carries_no_note_text(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_WRITE_NOTEBOOKS", "Inbox")
    result = await _create(notebook="Inbox", body="a long body nobody needs echoed back")
    assert "nobody needs echoed" not in json.dumps(result)
