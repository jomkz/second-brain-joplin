"""Tests for SemanticSearchService using in-memory fakes + respx-mocked Joplin."""

import asyncio
import re
import threading

import httpx
import pytest
import respx
from fakes import FakeEmbedder, FakeJoplin, FakeVectorIndex, SharedVectorIndex

from second_brain_joplin.config import Settings
from second_brain_joplin.errors import JoplinAPIError, JoplinConnectionError, NotebookFilterError
from second_brain_joplin.joplin_client import JoplinClient
from second_brain_joplin.semantic.service import SemanticSearchService
from second_brain_joplin.semantic.types import ChunkRecord, Embedder, VectorIndex

BASE_URL = "http://localhost:41184"


class Vault:
    """A mutable set of notes wired up as respx routes."""

    def __init__(self) -> None:
        self.notes: dict[str, dict[str, object]] = {}
        self.note_error: int | None = None

    def set(self, note_id: str, title: str, body: str, updated_time: int) -> None:
        self.notes[note_id] = {"title": title, "body": body, "updated_time": updated_time}

    def delete(self, note_id: str) -> None:
        self.notes.pop(note_id, None)

    def install(self) -> None:
        respx.get(f"{BASE_URL}/notes").mock(side_effect=self._index)
        respx.get(url__regex=rf"{re.escape(BASE_URL)}/notes/[^/?]+").mock(side_effect=self._note)

    def _index(self, request: httpx.Request) -> httpx.Response:
        items = [{"id": nid, "updated_time": n["updated_time"]} for nid, n in self.notes.items()]
        return httpx.Response(200, json={"items": items, "has_more": False})

    def _note(self, request: httpx.Request) -> httpx.Response:
        if self.note_error is not None:
            return httpx.Response(self.note_error)
        nid = request.url.path.rsplit("/", 1)[-1]
        note = self.notes.get(nid)
        if note is None:
            return httpx.Response(404)
        return httpx.Response(
            200,
            json={
                "id": nid,
                "title": note["title"],
                "body": note["body"],
                "parent_id": "",
                "created_time": 0,
                "updated_time": note["updated_time"],
            },
        )


def _service(
    *,
    auto_sync: bool = True,
    embedder: Embedder | None = None,
    index: VectorIndex | None = None,
    notebooks: tuple[str, ...] = (),
    exclude_notebooks: tuple[str, ...] = (),
) -> SemanticSearchService:
    settings = Settings(
        joplin_base_url=BASE_URL,
        joplin_api_token="tok",
        semantic_auto_sync=auto_sync,
        notebooks=notebooks,
        exclude_notebooks=exclude_notebooks,
    )
    client = JoplinClient(settings)
    return SemanticSearchService(
        client,
        embedder or FakeEmbedder(),
        index or FakeVectorIndex(),
        settings,
    )


@respx.mock
async def test_full_sync_embeds_all_notes() -> None:
    vault = Vault()
    vault.set("a", "Apple", "apple banana cherry", 100)
    vault.set("b", "Dog", "dog elephant frog", 100)
    vault.install()

    index = FakeVectorIndex()
    stats = await _service(index=index).sync(full=True)

    assert (stats.added, stats.updated, stats.deleted, stats.total) == (2, 0, 0, 2)
    assert set(index.note_versions()) == {"a", "b"}
    assert index.model_name == "fake-model"


@respx.mock
async def test_incremental_second_sync_is_noop() -> None:
    vault = Vault()
    vault.set("a", "Apple", "apple banana", 100)
    vault.install()

    embedder = FakeEmbedder()
    index = FakeVectorIndex()
    service = _service(embedder=embedder, index=index)

    await service.sync()
    calls_after_first = embedder.doc_calls
    stats = await service.sync()

    assert (stats.added, stats.updated, stats.deleted) == (0, 0, 0)
    assert embedder.doc_calls == calls_after_first  # nothing re-embedded


@respx.mock
async def test_sync_handles_add_change_delete() -> None:
    vault = Vault()
    vault.set("a", "A", "alpha", 100)
    vault.set("b", "B", "beta", 100)
    vault.install()

    index = FakeVectorIndex()
    service = _service(index=index)
    await service.sync()

    vault.set("b", "B", "beta changed", 200)  # changed
    vault.set("c", "C", "gamma", 100)  # new
    vault.delete("a")  # removed

    stats = await service.sync()
    assert (stats.added, stats.updated, stats.deleted, stats.total) == (1, 1, 1, 2)
    assert set(index.note_versions()) == {"b", "c"}
    assert index.note_versions()["b"] == "200"


@respx.mock
async def test_model_change_triggers_full_rebuild() -> None:
    vault = Vault()
    vault.set("a", "A", "alpha", 100)
    vault.install()

    index = FakeVectorIndex()
    await _service(embedder=FakeEmbedder("m1"), index=index).sync()
    assert index.model_name == "m1"

    stats = await _service(embedder=FakeEmbedder("m2"), index=index).sync()
    assert index.model_name == "m2"
    assert stats.added == 1  # everything re-embedded after reset


@respx.mock
async def test_search_auto_syncs_then_ranks() -> None:
    vault = Vault()
    vault.set("a", "Apple", "apple banana cherry", 100)
    vault.set("b", "Dog", "dog elephant frog", 100)
    vault.install()

    results = await _service(auto_sync=True).search("apple", limit=5)
    assert results[0].id == "a"
    assert results[0].score > 0


@respx.mock
async def test_search_without_auto_sync_uses_existing_index() -> None:
    vault = Vault()
    vault.set("a", "Apple", "apple banana", 100)
    vault.install()

    index = FakeVectorIndex()
    service = _service(auto_sync=False, index=index)
    # No sync yet → empty index → no results.
    assert await service.search("apple") == []

    await service.sync()
    results = await service.search("apple")
    assert [r.id for r in results] == ["a"]


@respx.mock
async def test_search_empty_index_returns_empty() -> None:
    vault = Vault()
    vault.install()  # no notes
    assert await _service().search("anything") == []


@respx.mock
async def test_search_dedupes_chunks_to_one_result_per_note() -> None:
    vault = Vault()
    # body long enough to split into multiple chunks
    body = "apple " * 400
    vault.set("a", "Apple", body, 100)
    vault.install()

    results = await _service().search("apple", limit=5)
    assert [r.id for r in results] == ["a"]  # single deduped result


@respx.mock
async def test_empty_body_note_adds_no_chunks() -> None:
    vault = Vault()
    vault.set("a", "Title only", "   ", 100)
    vault.install()

    index = FakeVectorIndex()
    stats = await _service(index=index).sync()
    assert stats.added == 1  # counted as processed
    assert index.note_versions() == {}  # but no chunks stored
    assert await _service(index=index, auto_sync=False).search("title") == []


@respx.mock
async def test_get_note_error_propagates() -> None:
    vault = Vault()
    vault.set("a", "A", "alpha", 100)
    vault.note_error = 500
    vault.install()

    with pytest.raises(JoplinAPIError):
        await _service().sync()


@respx.mock
async def test_concurrent_sync_is_serialized() -> None:
    vault = Vault()
    vault.set("a", "A", "alpha", 100)
    vault.install()

    index = FakeVectorIndex()
    service = _service(index=index)
    stats_a, stats_b = await asyncio.gather(service.sync(), service.sync())

    # Both complete; the lock prevents interleaving, so the index is consistent.
    assert set(index.note_versions()) == {"a"}
    assert stats_a.total == 1 and stats_b.total == 1


# -- the notebook filter ---------------------------------------------------------

SECRET = "feelings nobody else should read"


def _filtered_vault() -> tuple[FakeJoplin, str, str, str, str]:
    """Work and Journal, a note in each: (joplin, work, journal, plan, diary)."""
    joplin = FakeJoplin()
    work, journal = joplin.notebook("Work"), joplin.notebook("Journal")
    plan = joplin.note("Plan", "apple plan", work)
    diary = joplin.note("Diary", f"apple {SECRET}", journal)
    joplin.install()
    return joplin, work, journal, plan, diary


@respx.mock
async def test_filter_keeps_hidden_notes_out_of_the_index() -> None:
    joplin, _work, _journal, plan, _diary = _filtered_vault()
    index = FakeVectorIndex()
    stats = await _service(index=index, exclude_notebooks=("Journal",)).sync()

    assert (stats.added, stats.total) == (1, 1)
    assert set(index.note_versions()) == {plan}
    assert SECRET not in index.stored_text()
    # The hidden note's body was never even fetched.
    assert joplin.count(f"/notes/{_diary}") == 0


@respx.mock
async def test_note_moved_out_of_sight_is_dropped_at_the_next_sync() -> None:
    joplin, _work, journal, plan, _diary = _filtered_vault()
    index = FakeVectorIndex()
    service = _service(index=index, notebooks=("Work",))
    await service.sync()
    assert set(index.note_versions()) == {plan}

    joplin.move(plan, journal)  # updated_time is unchanged: only the notebook moved
    stats = await service.sync()

    assert (stats.deleted, stats.total) == (1, 0)
    assert index.note_versions() == {}
    assert "apple plan" not in index.stored_text()


@respx.mock
async def test_note_moved_into_sight_is_added_at_the_next_sync() -> None:
    joplin, work, _journal, plan, diary = _filtered_vault()
    index = FakeVectorIndex()
    service = _service(index=index, notebooks=("Work",))
    await service.sync()

    joplin.move(diary, work)
    stats = await service.sync()

    assert (stats.added, stats.updated, stats.total) == (1, 0, 2)
    assert set(index.note_versions()) == {plan, diary}


@respx.mock
async def test_a_note_that_moves_between_the_listing_and_the_read_is_not_embedded() -> None:
    joplin, _work, journal, plan, _diary = _filtered_vault()
    # The listing says Work; by the time the body is read the note is in Journal.
    joplin.before_note = lambda note_id: joplin.move(note_id, journal)
    index = FakeVectorIndex()
    embedder = FakeEmbedder()

    stats = await _service(index=index, embedder=embedder, notebooks=("Work",)).sync()

    assert stats.added == 0
    assert index.note_versions() == {}
    assert embedder.doc_calls == 0
    assert joplin.count(f"/notes/{plan}") == 1


@respx.mock
async def test_hidden_notes_leave_the_index_even_when_an_embedding_then_fails() -> None:
    joplin, work, _journal, _plan, _diary = _filtered_vault()
    index = FakeVectorIndex()
    await _service(index=index).sync()  # no filter: the diary is indexed
    assert SECRET in index.stored_text()

    joplin.note("New", "apple new", work)  # something to embed
    joplin.note_status = 500  # and reading it fails
    with pytest.raises(JoplinAPIError):
        await _service(index=index, exclude_notebooks=("Journal",)).sync()

    assert SECRET not in index.stored_text()  # dropped before the failure


@respx.mock
async def test_a_filter_that_does_not_resolve_leaves_the_index_untouched() -> None:
    _joplin, _work, _journal, plan, _diary = _filtered_vault()
    index = FakeVectorIndex()
    await _service(index=index, notebooks=("Work",)).sync()

    broken = _service(index=index, notebooks=("Wrok",))
    for full in (False, True):  # not even a full rebuild may wipe it
        with pytest.raises(NotebookFilterError):
            await broken.sync(full=full)
    with pytest.raises(NotebookFilterError):
        await broken.search("apple")
    with pytest.raises(NotebookFilterError):
        await broken.prune()

    assert set(index.note_versions()) == {plan}


@respx.mock
async def test_a_full_rebuild_with_joplin_down_leaves_the_index_untouched() -> None:
    joplin, _work, _journal, plan, diary = _filtered_vault()
    index = FakeVectorIndex()
    service = _service(index=index)
    await service.sync()

    joplin.down = True
    with pytest.raises(JoplinConnectionError):
        await service.sync(full=True)

    assert set(index.note_versions()) == {plan, diary}


@respx.mock
async def test_search_without_auto_sync_still_drops_what_the_filter_now_hides() -> None:
    joplin, work, journal, plan, _diary = _filtered_vault()
    index = FakeVectorIndex()
    embedder = FakeEmbedder()
    service = _service(
        auto_sync=False, index=index, embedder=embedder, exclude_notebooks=("Journal",)
    )
    await service.sync()
    assert [r.id for r in await service.search("apple plan")] == [plan]
    embedded = embedder.doc_calls

    joplin.move(plan, journal)  # hidden since the last sync
    joplin.note("Fresh", "apple fresh", work)  # and something new, not yet indexed

    assert await service.search("apple plan") == []
    assert index.note_versions() == {}  # gone from the index, not just from the answer
    assert embedder.doc_calls == embedded  # the prune embedded nothing


@respx.mock
async def test_search_without_auto_sync_or_a_filter_does_not_ask_joplin() -> None:
    joplin, _work, _journal, _plan, _diary = _filtered_vault()
    service = _service(auto_sync=False)
    await service.sync()
    before = len(joplin.requests)
    assert await service.search("apple") != []
    assert len(joplin.requests) == before


@respx.mock
async def test_prune_reports_what_it_dropped() -> None:
    joplin, _work, journal, plan, _diary = _filtered_vault()
    index = FakeVectorIndex()
    service = _service(index=index, exclude_notebooks=("Journal",))

    assert await service.prune() == 0  # an empty index has nothing to drop

    await service.sync()
    assert await service.prune() == 0
    joplin.move(plan, journal)
    assert await service.prune() == 1
    assert index.note_versions() == {}


# -- an index other processes write to ---------------------------------------------


def _intruder(note_id: str, title: str, text: str) -> ChunkRecord:
    """A chunk as an unfiltered process would have written it for a hidden note."""
    return ChunkRecord(
        chunk_id=f"{note_id}::0",
        note_id=note_id,
        title=title,
        updated_time="100",
        chunk_index=0,
        text=text,
        embedding=FakeEmbedder().embed_documents([text])[0],
    )


@pytest.mark.parametrize("auto_sync", [True, False])
@respx.mock
async def test_a_hidden_note_another_process_indexed_is_never_returned(auto_sync: bool) -> None:
    """The index is a shared file: a reindex run without the server's filter embeds
    everything into it. A filtered search must return only what Joplin says is visible."""
    _joplin, _work, _journal, plan, diary = _filtered_vault()
    index = SharedVectorIndex()
    service = _service(auto_sync=auto_sync, index=index, exclude_notebooks=("Journal",))
    await service.sync()
    # The other process writes after this one has tidied the index, before it queries.
    index.intruders = [_intruder(diary, "Diary", f"apple {SECRET}")]

    results = await service.search(f"apple {SECRET}", limit=5)

    assert [r.id for r in results] == [plan]
    assert all(SECRET not in r.excerpt and r.title != "Diary" for r in results)
    assert diary in index.note_versions()  # it really was in the index when queried


@respx.mock
async def test_without_a_filter_whatever_is_indexed_is_returned() -> None:
    _joplin, _work, _journal, plan, diary = _filtered_vault()
    results = await _service(index=SharedVectorIndex()).search("apple", limit=5)
    assert {r.id for r in results} == {plan, diary}


class _SlowEmbedder(FakeEmbedder):
    """An embedder whose document embedding blocks until released, like a long rebuild."""

    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.started.set()
        assert self.release.wait(timeout=5)
        return super().embed_documents(texts)


@respx.mock
async def test_a_search_without_auto_sync_does_not_wait_behind_a_running_sync() -> None:
    joplin, work, _journal, plan, _diary = _filtered_vault()
    index = FakeVectorIndex()
    await _service(index=index, exclude_notebooks=("Journal",)).sync()

    joplin.note("New", "apple new", work)  # gives the next sync something slow to embed
    slow = _SlowEmbedder()
    service = _service(auto_sync=False, index=index, embedder=slow, exclude_notebooks=("Journal",))
    syncing = asyncio.create_task(service.sync())
    await asyncio.to_thread(slow.started.wait, 5)
    try:
        # The sync holds the index; the search answers from what is there, filtered.
        results = await asyncio.wait_for(service.search("apple plan"), timeout=2)
        assert [r.id for r in results] == [plan]
        assert not syncing.done()
    finally:
        slow.release.set()
        await syncing
