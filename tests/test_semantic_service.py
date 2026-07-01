"""Tests for SemanticSearchService using in-memory fakes + respx-mocked Joplin."""

import asyncio
import re

import httpx
import pytest
import respx
from fakes import FakeEmbedder, FakeVectorIndex

from second_brain_joplin.config import Settings
from second_brain_joplin.errors import JoplinAPIError
from second_brain_joplin.joplin_client import JoplinClient
from second_brain_joplin.semantic.service import SemanticSearchService
from second_brain_joplin.semantic.types import Embedder, VectorIndex

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
) -> SemanticSearchService:
    settings = Settings(
        joplin_base_url=BASE_URL,
        joplin_api_token="tok",
        semantic_auto_sync=auto_sync,
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
