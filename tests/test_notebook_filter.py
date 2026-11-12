"""The notebook filter seen through the tools: what a client can and cannot reach.

Every test drives the real tools through a FastMCP client against an in-memory
Joplin, with SBJ_NOTEBOOKS / SBJ_EXCLUDE_NOTEBOOKS set in the environment the way
an operator would set them.
"""

import json
import logging
import time
from collections.abc import Iterator
from typing import Any

import pytest
import respx
from fakes import FakeEmbedder, FakeJoplin, FakeVectorIndex
from fastmcp import Client
from fastmcp.exceptions import ToolError

from second_brain_joplin.errors import NOT_FOUND_MESSAGE, NOTEBOOK_FILTER_MESSAGE
from second_brain_joplin.semantic import backends
from second_brain_joplin.server import mcp

SECRET = "feelings nobody else should read"


def _now_ms(seconds_ago: float = 0) -> int:
    return int((time.time() - seconds_ago) * 1000)


class Vault:
    """Work ─ Projects   and   Journal, with one note in each."""

    def __init__(self, joplin: FakeJoplin) -> None:
        self.joplin = joplin
        self.work = joplin.notebook("Work")
        self.projects = joplin.notebook("Projects", parent=self.work)
        self.journal = joplin.notebook("Journal")
        self.roadmap = joplin.note("Roadmap", "apple roadmap", self.work, _now_ms(30))
        self.sprint = joplin.note("Sprint", "apple sprint", self.projects, _now_ms(20))
        self.diary = joplin.note("Diary", f"apple {SECRET}", self.journal, _now_ms(10))


@pytest.fixture
def joplin() -> Iterator[FakeJoplin]:
    with respx.mock:
        fake = FakeJoplin()
        fake.install()
        yield fake


@pytest.fixture
def vault(joplin: FakeJoplin) -> Vault:
    return Vault(joplin)


@pytest.fixture
def index(monkeypatch: pytest.MonkeyPatch) -> FakeVectorIndex:
    """Semantic search on in-memory fakes; the index is returned for inspection."""
    shared = FakeVectorIndex()
    monkeypatch.setattr(backends, "build_embedder", lambda settings: FakeEmbedder())
    monkeypatch.setattr(backends, "build_vector_index", lambda settings, model_name: shared)
    return shared


async def _call(tool: str, **args: Any) -> Any:
    async with Client(mcp) as client:
        return (await client.call_tool(tool, args)).structured_content


async def _error(tool: str, **args: Any) -> str:
    async with Client(mcp) as client:
        with pytest.raises(ToolError) as raised:
            await client.call_tool(tool, args)
    return str(raised.value)


def _ids(result: Any) -> list[str]:
    return [item["id"] for item in result["result"]]


# -- joplin_overview ------------------------------------------------------------


async def test_overview_leaves_out_an_excluded_notebook(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_EXCLUDE_NOTEBOOKS", "Journal")
    result = await _call("joplin_overview")
    tree = result["result"]
    assert [(n["name"], n["note_count"]) for n in tree] == [("Work", 1)]
    assert [(n["name"], n["note_count"]) for n in tree[0]["children"]] == [("Projects", 1)]
    assert "Journal" not in json.dumps(result)
    assert vault.journal not in json.dumps(result)


async def test_overview_puts_a_visible_notebook_under_a_hidden_parent_at_the_top(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_NOTEBOOKS", vault.projects)
    result = await _call("joplin_overview")
    assert [n["name"] for n in result["result"]] == ["Projects"]
    assert "Work" not in json.dumps(result)  # the hidden parent's name never appears


async def test_overview_drops_an_excluded_subtree_of_an_included_notebook(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    deep = vault.joplin.notebook("Deep", parent=vault.projects)
    monkeypatch.setenv("SBJ_NOTEBOOKS", "Work")
    monkeypatch.setenv("SBJ_EXCLUDE_NOTEBOOKS", "Projects")
    result = await _call("joplin_overview")
    assert [(n["name"], n["children"]) for n in result["result"]] == [("Work", [])]
    assert deep not in json.dumps(result)


async def test_overview_without_a_filter_shows_every_notebook(vault: Vault) -> None:
    result = await _call("joplin_overview")
    assert sorted(n["name"] for n in result["result"]) == ["Journal", "Work"]


# -- joplin_search --------------------------------------------------------------


async def test_search_leaves_out_hits_in_a_hidden_notebook(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_EXCLUDE_NOTEBOOKS", vault.journal)
    result = await _call("joplin_search", query="apple")
    assert _ids(result) == [vault.roadmap, vault.sprint]
    assert SECRET not in json.dumps(result)


async def test_search_keeps_paging_until_the_limit_is_filled(
    joplin: FakeJoplin, monkeypatch: pytest.MonkeyPatch
) -> None:
    joplin.page_size = 2
    work, journal = joplin.notebook("Work"), joplin.notebook("Journal")
    visible = []
    for n in range(6):  # hidden and visible hits alternate, hidden first
        joplin.note(f"Hidden {n}", "apple", journal)
        visible.append(joplin.note(f"Visible {n}", "apple", work))
    monkeypatch.setenv("SBJ_NOTEBOOKS", "Work")

    result = await _call("joplin_search", query="apple", limit=4)

    # Four raw hits would hold only two visible ones; the walk went on for the rest,
    # in Joplin's order, and stopped as soon as it had them.
    assert _ids(result) == visible[:4]
    assert joplin.count("/search") == 4


async def test_search_that_matches_only_hidden_notes_is_empty(
    joplin: FakeJoplin, monkeypatch: pytest.MonkeyPatch
) -> None:
    joplin.page_size = 2
    joplin.notebook("Work")
    journal = joplin.notebook("Journal")
    for n in range(5):
        joplin.note(f"Hidden {n}", "apple", journal)
    monkeypatch.setenv("SBJ_NOTEBOOKS", "Work")
    assert _ids(await _call("joplin_search", query="apple")) == []
    assert joplin.count("/search") == 3  # every page was looked at, none let through


# -- joplin_recent --------------------------------------------------------------


async def test_recent_leaves_out_notes_in_a_hidden_notebook(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_EXCLUDE_NOTEBOOKS", "Journal")
    result = await _call("joplin_recent")
    assert _ids(result) == [vault.sprint, vault.roadmap]  # newest first, no Diary
    assert "Diary" not in json.dumps(result)


async def test_recent_keeps_paging_until_the_limit_is_filled(
    joplin: FakeJoplin, monkeypatch: pytest.MonkeyPatch
) -> None:
    joplin.page_size = 2
    work, journal = joplin.notebook("Work"), joplin.notebook("Journal")
    visible = []
    for n in range(6):  # newest first: hidden, visible, hidden, visible, ...
        joplin.note(f"Hidden {n}", "x", journal, _now_ms(10 * n))
        visible.append(joplin.note(f"Visible {n}", "x", work, _now_ms(10 * n + 5)))
    monkeypatch.setenv("SBJ_EXCLUDE_NOTEBOOKS", "Journal")

    result = await _call("joplin_recent", limit=3)

    assert _ids(result) == visible[:3]
    assert joplin.count("/notes") == 3


async def test_recent_stops_at_the_first_note_older_than_the_window(
    joplin: FakeJoplin, monkeypatch: pytest.MonkeyPatch
) -> None:
    joplin.page_size = 2
    work, journal = joplin.notebook("Work"), joplin.notebook("Journal")
    fresh = joplin.note("Fresh", "x", work, _now_ms(60))
    joplin.note("Fresh but hidden", "x", journal, _now_ms(120))
    month = 60 * 60 * 24 * 30
    for n in range(20):  # a long tail of old notes, visible ones among them
        joplin.note(f"Old {n}", "x", work, _now_ms(month + n))
    monkeypatch.setenv("SBJ_EXCLUDE_NOTEBOOKS", "Journal")

    result = await _call("joplin_recent", days=7, limit=10)

    assert _ids(result) == [fresh]
    # One visible note in the window, a limit of ten: without the stop the walk
    # would read all eleven pages looking for nine more. It read two.
    assert joplin.count("/notes") == 2


async def test_recent_without_a_filter_still_honours_the_window(joplin: FakeJoplin) -> None:
    work = joplin.notebook("Work")
    new = joplin.note("New", "x", work, _now_ms(60))
    joplin.note("Old", "x", work, _now_ms(60 * 60 * 24 * 30))
    assert _ids(await _call("joplin_recent", days=7)) == [new]
    assert joplin.count("/folders") == 0  # no filter, no extra request


# -- joplin_read ----------------------------------------------------------------


async def test_reading_a_hidden_note_answers_exactly_like_a_missing_one(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_EXCLUDE_NOTEBOOKS", "Journal")
    hidden = await _error("joplin_read", note_id=vault.diary)
    missing = await _error("joplin_read", note_id="f" * 32)
    assert hidden == missing == NOT_FOUND_MESSAGE
    assert SECRET not in hidden


async def test_reading_a_visible_note_works_with_a_filter_set(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_EXCLUDE_NOTEBOOKS", "Journal")
    result = await _call("joplin_read", note_id=vault.sprint)
    assert (result["title"], result["body"]) == ("Sprint", "apple sprint")


async def test_a_note_with_no_notebook_is_hidden_once_a_filter_is_set(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    orphan = vault.joplin.note("Orphan", "apple orphan", "")
    assert (await _call("joplin_read", note_id=orphan))["title"] == "Orphan"
    monkeypatch.setenv("SBJ_EXCLUDE_NOTEBOOKS", "Journal")
    assert await _error("joplin_read", note_id=orphan) == NOT_FOUND_MESSAGE


# -- a note that moves ----------------------------------------------------------


async def test_a_note_moved_between_notebooks_changes_at_the_next_call(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_NOTEBOOKS", "Work")
    assert (await _call("joplin_read", note_id=vault.sprint))["title"] == "Sprint"

    vault.joplin.move(vault.sprint, vault.journal)  # out of sight
    assert await _error("joplin_read", note_id=vault.sprint) == NOT_FOUND_MESSAGE
    assert _ids(await _call("joplin_search", query="apple")) == [vault.roadmap]
    assert _ids(await _call("joplin_recent")) == [vault.roadmap]

    vault.joplin.move(vault.diary, vault.work)  # and one into sight
    assert (await _call("joplin_read", note_id=vault.diary))["title"] == "Diary"
    assert _ids(await _call("joplin_search", query="apple")) == [vault.roadmap, vault.diary]


# -- semantic search ------------------------------------------------------------


async def test_semantic_search_never_indexes_or_returns_a_hidden_note(
    vault: Vault, index: FakeVectorIndex, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_EXCLUDE_NOTEBOOKS", "Journal")
    result = await _call("joplin_semantic_search", query=f"apple {SECRET}")
    assert sorted(_ids(result)) == sorted([vault.roadmap, vault.sprint])
    assert set(index.note_versions()) == {vault.roadmap, vault.sprint}
    assert SECRET not in index.stored_text()
    assert "Diary" not in index.stored_text()


async def test_reindex_counts_only_what_the_filter_shows(
    vault: Vault, index: FakeVectorIndex, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_NOTEBOOKS", vault.projects)
    result = await _call("joplin_reindex", full=True)
    assert (result["added"], result["total"]) == (1, 1)
    assert set(index.note_versions()) == {vault.sprint}


async def test_changing_the_filter_drops_newly_hidden_notes_from_the_index(
    vault: Vault, index: FakeVectorIndex, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _call("joplin_reindex")  # no filter yet: everything is indexed
    assert SECRET in index.stored_text()

    monkeypatch.setenv("SBJ_EXCLUDE_NOTEBOOKS", "Journal")
    result = await _call("joplin_reindex")  # a plain sync, not a full rebuild

    assert (result["deleted"], result["total"]) == (1, 2)
    assert SECRET not in index.stored_text()


# -- a filter that doesn't resolve ----------------------------------------------

ALL_TOOLS: list[tuple[str, dict[str, Any]]] = [
    ("joplin_overview", {}),
    ("joplin_search", {"query": "apple"}),
    ("joplin_read", {"note_id": "f" * 32}),
    ("joplin_recent", {}),
    ("joplin_semantic_search", {"query": "apple"}),
    ("joplin_reindex", {}),
]


@pytest.mark.parametrize(("tool", "args"), ALL_TOOLS)
async def test_every_tool_refuses_while_the_filter_does_not_resolve(
    tool: str,
    args: dict[str, Any],
    vault: Vault,
    index: FakeVectorIndex,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("SBJ_EXCLUDE_NOTEBOOKS", "Secret diary")  # no such notebook
    message = await _error(tool, **args)

    assert message == NOTEBOOK_FILTER_MESSAGE
    assert "Secret diary" not in message  # the client learns no notebook's name
    # The operator does, in the log.
    assert "SBJ_EXCLUDE_NOTEBOOKS: no notebook is titled 'Secret diary'" in caplog.text
    # Nothing was read from Joplin beyond its notebook list, and nothing indexed.
    assert set(vault.joplin.requests) == {"/folders"}
    assert index.note_versions() == {}


async def test_renaming_a_notebook_excluded_by_title_fails_closed(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_EXCLUDE_NOTEBOOKS", "Journal")
    assert _ids(await _call("joplin_search", query="apple")) == [vault.roadmap, vault.sprint]

    vault.joplin.folders[vault.journal]["title"] = "Diary 2026"

    # The title no longer names anything: refusing is the only safe reading.
    assert await _error("joplin_search", query="apple") == NOTEBOOK_FILTER_MESSAGE
    assert await _error("joplin_read", note_id=vault.roadmap) == NOTEBOOK_FILTER_MESSAGE


async def test_renaming_a_notebook_excluded_by_id_changes_nothing(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SBJ_EXCLUDE_NOTEBOOKS", vault.journal)
    vault.joplin.folders[vault.journal]["title"] = "Diary 2026"
    assert _ids(await _call("joplin_search", query="apple")) == [vault.roadmap, vault.sprint]


async def test_a_failed_semantic_sync_does_not_log_the_filter_detail_twice(
    vault: Vault,
    index: FakeVectorIndex,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="second_brain_joplin")
    monkeypatch.setenv("SBJ_NOTEBOOKS", "Wrok")
    await _error("joplin_semantic_search", query="apple")
    assert caplog.text.count("no notebook is titled 'Wrok'") == 1
