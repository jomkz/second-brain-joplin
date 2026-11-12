"""Tests for the notebook filter: how SBJ_NOTEBOOKS / SBJ_EXCLUDE_NOTEBOOKS resolve."""

import logging

import pytest
import respx
from fakes import FakeJoplin

from second_brain_joplin.config import Settings
from second_brain_joplin.errors import NOTEBOOK_FILTER_MESSAGE, NotebookFilterError
from second_brain_joplin.joplin_client import JoplinClient, JsonDict
from second_brain_joplin.scope import (
    UNFILTERED,
    NotebookScope,
    check_at_startup,
    current_scope,
    current_write_targets,
    resolve_scope,
    resolve_write_targets,
    scope_of,
)

BASE_URL = "http://localhost:41184"


def _id(n: int) -> str:
    return f"{n:032x}"


WORK, PROJECTS, ALPHA, JOURNAL, PRIVATE, ARCHIVE_A, ARCHIVE_B = (_id(n) for n in range(1, 8))

# Work ─ Projects ─ Alpha        Journal ─ Private        Archive (under Work)
#      └ Archive                                          Archive (under Journal)
FOLDERS: list[JsonDict] = [
    {"id": WORK, "title": "Work", "parent_id": ""},
    {"id": PROJECTS, "title": "Projects", "parent_id": WORK},
    {"id": ALPHA, "title": "Alpha", "parent_id": PROJECTS},
    {"id": JOURNAL, "title": "Journal", "parent_id": ""},
    {"id": PRIVATE, "title": "Private", "parent_id": JOURNAL},
    {"id": ARCHIVE_A, "title": "Archive", "parent_id": WORK},
    {"id": ARCHIVE_B, "title": "Archive", "parent_id": JOURNAL},
]
ALL = {WORK, PROJECTS, ALPHA, JOURNAL, PRIVATE, ARCHIVE_A, ARCHIVE_B}


def _visible(include: list[str], exclude: list[str]) -> set[str]:
    scope = resolve_scope(include, exclude, FOLDERS)
    assert scope.visible is not None
    return set(scope.visible)


def _detail(include: list[str], exclude: list[str]) -> str:
    with pytest.raises(NotebookFilterError) as raised:
        resolve_scope(include, exclude, FOLDERS)
    return raised.value.detail


# -- what a filter shows --------------------------------------------------------


def test_no_filter_allows_everything_including_unknown_notebooks() -> None:
    scope = resolve_scope([], [], FOLDERS)
    assert scope is UNFILTERED
    assert scope.visible is None
    assert scope.allows(WORK)
    assert scope.allows("")  # a note with no notebook
    assert scope.allows_note({"id": "n"})  # no parent_id at all


def test_include_by_id_covers_the_notebook_and_everything_under_it() -> None:
    assert _visible([WORK], []) == {WORK, PROJECTS, ALPHA, ARCHIVE_A}


def test_include_a_nested_notebook_leaves_its_parent_out() -> None:
    assert _visible([PROJECTS], []) == {PROJECTS, ALPHA}


def test_include_by_title() -> None:
    assert _visible(["Journal"], []) == {JOURNAL, PRIVATE, ARCHIVE_B}


def test_several_includes_are_a_union() -> None:
    assert _visible(["Alpha", PRIVATE], []) == {ALPHA, PRIVATE}


def test_exclude_alone_hides_a_subtree_and_shows_the_rest() -> None:
    assert _visible([], ["Journal"]) == {WORK, PROJECTS, ALPHA, ARCHIVE_A}


def test_exclude_carves_a_subtree_out_of_an_included_notebook() -> None:
    assert _visible([WORK], [PROJECTS]) == {WORK, ARCHIVE_A}


def test_excluding_everything_shows_nothing() -> None:
    scope = resolve_scope([], [WORK, JOURNAL], FOLDERS)
    assert scope.visible == frozenset()
    assert not scope.allows(WORK)


def test_an_uppercase_id_is_still_an_id() -> None:
    upper = f"{0xABC:032X}"
    folders = [{"id": upper.lower(), "title": "Hex", "parent_id": ""}]
    assert resolve_scope([upper], [], folders).visible == frozenset({upper.lower()})


def test_a_filtered_scope_hides_notes_whose_notebook_is_unknown() -> None:
    scope = resolve_scope([WORK], [], FOLDERS)
    assert scope.allows_note({"id": "n", "parent_id": ALPHA})
    assert not scope.allows_note({"id": "n", "parent_id": JOURNAL})
    assert not scope.allows_note({"id": "n", "parent_id": ""})
    assert not scope.allows_note({"id": "n"})
    assert not scope.allows_note({"id": "n", "parent_id": _id(999)})


def test_a_notebook_created_under_a_visible_one_is_visible_at_the_next_resolve() -> None:
    new = _id(50)
    grown = [*FOLDERS, {"id": new, "title": "Beta", "parent_id": PROJECTS}]
    assert new in (resolve_scope([WORK], [], grown).visible or set())
    assert new not in (resolve_scope([WORK], [PROJECTS], grown).visible or set())


def test_a_notebook_moved_under_a_hidden_one_is_hidden_at_the_next_resolve() -> None:
    moved = [dict(f, parent_id=JOURNAL) if f["id"] == PROJECTS else f for f in FOLDERS]
    assert _visible([], ["Journal"]) >= {PROJECTS, ALPHA}
    assert resolve_scope([], ["Journal"], moved).visible == frozenset({WORK, ARCHIVE_A})


def test_a_cycle_in_the_notebook_list_does_not_loop() -> None:
    a, b = _id(1), _id(2)
    folders = [
        {"id": a, "title": "A", "parent_id": b},
        {"id": b, "title": "B", "parent_id": a},
    ]
    assert resolve_scope([a], [], folders).visible == frozenset({a, b})


def test_with_only_an_exclude_list_a_notebook_that_cannot_be_traced_stays_hidden() -> None:
    top, private, leaf, loop_a, loop_b = (_id(n) for n in range(1, 6))
    folders = [
        {"id": top, "title": "Top", "parent_id": ""},
        {"id": private, "title": "Private", "parent_id": ""},
        # Leaf sits under a notebook the list doesn't contain. That notebook could
        # be inside Private, so Leaf can't be shown.
        {"id": leaf, "title": "Leaf", "parent_id": _id(99)},
        # Two notebooks that contain each other: nothing says what they are under.
        {"id": loop_a, "title": "Loop A", "parent_id": loop_b},
        {"id": loop_b, "title": "Loop B", "parent_id": loop_a},
    ]
    assert resolve_scope([], ["Private"], folders).visible == frozenset({top})
    # Naming such a notebook outright in SBJ_NOTEBOOKS still shows it.
    assert resolve_scope([leaf], [], folders).visible == frozenset({leaf})


# -- filters that are refused ---------------------------------------------------


def test_an_id_no_notebook_has_is_refused() -> None:
    assert _detail([_id(999)], []) == f"SBJ_NOTEBOOKS: no notebook has the id {_id(999)}"
    assert _detail([], [_id(999)]).startswith("SBJ_EXCLUDE_NOTEBOOKS: no notebook has the id")


def test_a_title_no_notebook_has_is_refused() -> None:
    assert _detail(["Jurnal"], []) == "SBJ_NOTEBOOKS: no notebook is titled 'Jurnal'"
    assert _detail([], ["Jurnal"]) == "SBJ_EXCLUDE_NOTEBOOKS: no notebook is titled 'Jurnal'"


def test_titles_match_exactly() -> None:
    assert "no notebook is titled 'journal'" in _detail(["journal"], [])
    assert "no notebook is titled 'Journ'" in _detail(["Journ"], [])


def test_a_title_two_notebooks_share_is_refused_and_names_their_ids() -> None:
    detail = _detail([], ["Archive"])
    assert detail.startswith("SBJ_EXCLUDE_NOTEBOOKS: 2 notebooks are titled 'Archive'")
    assert ARCHIVE_A in detail and ARCHIVE_B in detail


def test_an_included_notebook_that_is_also_hidden_is_refused() -> None:
    assert "'Journal' is hidden by SBJ_EXCLUDE_NOTEBOOKS" in _detail(["Journal"], ["Journal"])
    # Hidden through its parent: listing it could never show it.
    assert f"{PRIVATE!r} is hidden by SBJ_EXCLUDE_NOTEBOOKS" in _detail([PRIVATE], ["Journal"])


def test_one_bad_entry_refuses_the_whole_filter() -> None:
    assert "no notebook is titled 'Nope'" in _detail(["Work", "Nope"], [])


def test_the_error_a_client_sees_never_carries_the_detail() -> None:
    with pytest.raises(NotebookFilterError) as raised:
        resolve_scope([], ["Secret diary"], FOLDERS)
    assert str(raised.value) == NOTEBOOK_FILTER_MESSAGE
    assert "Secret diary" not in str(raised.value)
    assert "Secret diary" in raised.value.detail


# -- resolving against Joplin ---------------------------------------------------


def _settings(
    notebooks: tuple[str, ...] = (),
    exclude_notebooks: tuple[str, ...] = (),
    write_notebooks: tuple[str, ...] = (),
) -> Settings:
    return Settings(
        joplin_base_url=BASE_URL,
        joplin_api_token="tok",
        notebooks=notebooks,
        exclude_notebooks=exclude_notebooks,
        write_notebooks=write_notebooks,
    )


@respx.mock
async def test_current_scope_without_a_filter_does_not_ask_joplin() -> None:
    joplin = FakeJoplin()
    joplin.install()
    settings = _settings()
    assert await current_scope(JoplinClient(settings), settings) is UNFILTERED
    assert joplin.requests == []


@respx.mock
async def test_current_scope_resolves_against_joplin_every_time() -> None:
    joplin = FakeJoplin()
    work = joplin.notebook("Work")
    joplin.install()
    settings = _settings(notebooks=("Work",))
    client = JoplinClient(settings)

    assert await current_scope(client, settings) == NotebookScope(frozenset({work}))
    sub = joplin.notebook("Sub", parent=work)
    assert await current_scope(client, settings) == NotebookScope(frozenset({work, sub}))
    assert joplin.count("/folders") == 2  # never cached


@respx.mock
async def test_current_scope_follows_joplins_pagination() -> None:
    joplin = FakeJoplin(page_size=2)
    work = joplin.notebook("Work")
    subs = {joplin.notebook(f"Sub {n}", parent=work) for n in range(5)}
    joplin.install()
    settings = _settings(notebooks=(work,))
    scope = await current_scope(JoplinClient(settings), settings)
    assert scope.visible == frozenset({work} | subs)


@respx.mock
async def test_startup_check_passes_a_good_filter_and_logs_only_counts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="second_brain_joplin")
    joplin = FakeJoplin()
    joplin.notebook("Work")
    joplin.notebook("Secret diary")
    joplin.install()
    await check_at_startup(_settings(exclude_notebooks=("Secret diary",)))
    assert "notebook filter: 1 of 2 notebooks visible" in caplog.text
    assert "Secret diary" not in caplog.text


@respx.mock
async def test_startup_check_refuses_a_wrong_filter() -> None:
    joplin = FakeJoplin()
    joplin.notebook("Work")
    joplin.install()
    with pytest.raises(NotebookFilterError) as raised:
        await check_at_startup(_settings(notebooks=("Wrok",)))
    assert raised.value.detail == "SBJ_NOTEBOOKS: no notebook is titled 'Wrok'"


@respx.mock
async def test_startup_check_lets_the_server_start_when_joplin_is_down(
    caplog: pytest.LogCaptureFixture,
) -> None:
    joplin = FakeJoplin()
    joplin.down = True
    joplin.install()
    await check_at_startup(_settings(notebooks=("Work",)))  # no error
    assert "couldn't be checked at start-up" in caplog.text
    assert "checked again on every call" in caplog.text


@respx.mock
async def test_startup_check_without_a_filter_does_nothing() -> None:
    joplin = FakeJoplin()
    joplin.down = True
    joplin.install()
    await check_at_startup(_settings())
    assert joplin.requests == []


# -- where a note may be created (SBJ_WRITE_NOTEBOOKS) ----------------------------


def _writable(write: list[str], include: list[str], exclude: list[str]) -> set[str]:
    scope = resolve_scope(include, exclude, FOLDERS)
    return set(resolve_write_targets(write, scope, FOLDERS).titles)


def _write_detail(write: list[str], include: list[str], exclude: list[str]) -> str:
    scope = resolve_scope(include, exclude, FOLDERS)
    with pytest.raises(NotebookFilterError) as raised:
        resolve_write_targets(write, scope, FOLDERS)
    return raised.value.detail


def test_no_write_list_means_nowhere() -> None:
    targets = resolve_write_targets([], UNFILTERED, FOLDERS)
    assert targets.titles == {}
    assert targets.title_of(WORK) is None


def test_a_write_entry_covers_the_notebook_and_everything_under_it() -> None:
    assert _writable([WORK], [], []) == {WORK, PROJECTS, ALPHA, ARCHIVE_A}
    assert _writable(["Projects"], [], []) == {PROJECTS, ALPHA}
    assert _writable(["Alpha", PRIVATE], [], []) == {ALPHA, PRIVATE}


def test_write_targets_carry_each_notebooks_title() -> None:
    targets = resolve_write_targets(["Projects"], UNFILTERED, FOLDERS)
    assert targets.titles == {PROJECTS: "Projects", ALPHA: "Alpha"}
    assert targets.title_of(ALPHA) == "Alpha"


def test_a_star_means_every_notebook_the_filter_shows() -> None:
    assert _writable(["*"], [], []) == ALL
    assert _writable(["*"], [], ["Journal"]) == {WORK, PROJECTS, ALPHA, ARCHIVE_A}
    assert _writable(["*"], [PROJECTS], []) == {PROJECTS, ALPHA}
    assert _writable(["*", "Work"], [], ["Journal"]) == {WORK, PROJECTS, ALPHA, ARCHIVE_A}


def test_writing_never_reaches_past_the_filter() -> None:
    # Work is listed for writing, but the filter hides Projects (and Alpha under it).
    assert _writable([WORK], [], [PROJECTS]) == {WORK, ARCHIVE_A}
    assert _writable([WORK], [WORK], [PROJECTS]) == {WORK, ARCHIVE_A}


def test_a_write_entry_the_filter_hides_is_refused() -> None:
    assert _write_detail(["Journal"], [], ["Journal"]) == (
        "SBJ_WRITE_NOTEBOOKS: 'Journal' is hidden by the notebook filter, so no note "
        "could be created there"
    )
    assert "is hidden by the notebook filter" in _write_detail([PRIVATE], [], ["Journal"])
    assert "is hidden by the notebook filter" in _write_detail(["Journal"], [WORK], [])


def test_a_write_entry_that_names_nothing_or_too_much_is_refused() -> None:
    assert _write_detail(["Inbocks"], [], []) == (
        "SBJ_WRITE_NOTEBOOKS: no notebook is titled 'Inbocks'"
    )
    assert _write_detail([_id(999)], [], []).startswith(
        "SBJ_WRITE_NOTEBOOKS: no notebook has the id"
    )
    assert "2 notebooks are titled 'Archive'" in _write_detail(["Archive"], [], [])


@respx.mock
async def test_current_write_targets_does_not_ask_joplin_while_writes_are_off() -> None:
    joplin = FakeJoplin()
    joplin.install()
    settings = _settings(exclude_notebooks=("Journal",))
    assert (await current_write_targets(JoplinClient(settings), settings)).titles == {}
    assert joplin.requests == []


@respx.mock
async def test_current_write_targets_follow_joplin_and_the_filter() -> None:
    joplin = FakeJoplin()
    work, journal = joplin.notebook("Work"), joplin.notebook("Journal")
    joplin.install()
    settings = _settings(exclude_notebooks=("Journal",), write_notebooks=("*",))
    client = JoplinClient(settings)

    assert (await current_write_targets(client, settings)).titles == {work: "Work"}
    sub = joplin.notebook("Sub", parent=work)
    joplin.notebook("Hidden sub", parent=journal)
    assert (await current_write_targets(client, settings)).titles == {work: "Work", sub: "Sub"}


@respx.mock
async def test_startup_check_covers_the_write_list_even_without_a_filter(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="second_brain_joplin")
    joplin = FakeJoplin()
    work = joplin.notebook("Work")
    joplin.notebook("Sub", parent=work)
    joplin.notebook("Journal")
    joplin.install()

    await check_at_startup(_settings(write_notebooks=("Work",)))
    assert "note creation: allowed in 2 notebooks" in caplog.text
    assert "notebook filter:" not in caplog.text  # none is set, so none is reported

    with pytest.raises(NotebookFilterError) as raised:
        await check_at_startup(_settings(write_notebooks=("Wrok",)))
    assert raised.value.detail == "SBJ_WRITE_NOTEBOOKS: no notebook is titled 'Wrok'"


# -- a filter variable that is set but lists nothing ------------------------------


def test_a_blank_filter_variable_is_refused_not_read_as_no_filter() -> None:
    settings = Settings(blank_filter_vars=("SBJ_NOTEBOOKS",))
    with pytest.raises(NotebookFilterError) as raised:
        scope_of(settings, FOLDERS)
    assert raised.value.detail == (
        "SBJ_NOTEBOOKS: set, but lists no notebook; list at least one, or remove the variable"
    )


@respx.mock
async def test_a_blank_filter_variable_stops_every_call_and_the_start() -> None:
    joplin = FakeJoplin()
    joplin.notebook("Work")
    joplin.down = True  # it is wrong whatever Joplin says, so Joplin isn't even asked
    joplin.install()
    settings = Settings(
        joplin_base_url=BASE_URL, blank_filter_vars=("SBJ_NOTEBOOKS", "SBJ_EXCLUDE_NOTEBOOKS")
    )
    with pytest.raises(NotebookFilterError, match="notebook settings") as raised:
        await check_at_startup(settings)
    assert raised.value.detail.startswith("SBJ_NOTEBOOKS and SBJ_EXCLUDE_NOTEBOOKS: set, but")
    assert joplin.requests == []

    joplin.down = False
    with pytest.raises(NotebookFilterError):
        await current_scope(JoplinClient(settings), settings)


@respx.mock
async def test_startup_says_so_when_no_filter_is_set(caplog: pytest.LogCaptureFixture) -> None:
    """A misspelt variable name must not pass for a filter in the log."""
    caplog.set_level(logging.INFO, logger="second_brain_joplin")
    joplin = FakeJoplin()
    joplin.notebook("Inbox")
    joplin.install()
    await check_at_startup(_settings())
    assert "no notebook filter is set: every notebook is readable" in caplog.text
    assert joplin.requests == []

    caplog.clear()
    await check_at_startup(_settings(write_notebooks=("Inbox",)))  # writing is no filter
    assert "no notebook filter is set" in caplog.text
    assert "note creation: allowed in 1 notebooks" in caplog.text
