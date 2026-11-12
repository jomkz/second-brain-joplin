"""Orchestrates embedding sync and semantic search over Joplin notes.

Pure orchestration: it takes an already-built :class:`Embedder` and
:class:`VectorIndex` (see :mod:`.types`) by dependency injection and never
imports an optional dependency, so it is fully exercised in tests with in-memory
fakes. CPU-bound embedder/index calls are pushed to worker threads via
``asyncio.to_thread`` and serialized with a lock so concurrent tool calls cannot
corrupt the store.

The notebook filter (scope.py) decides what the index may hold: a note the filter
hides is never embedded, and one that becomes hidden (it moved, its notebook
moved, or the filter changed) is dropped by the next sync, before anything new is
embedded. A search with a filter set never runs against an index that hasn't
just been reconciled with it.
"""

import asyncio

from ..config import Settings
from ..joplin_client import JoplinClient
from ..models import SemanticResult, excerpt
from ..scope import NotebookScope, current_scope
from .chunking import chunk_note
from .sync import diff_versions
from .types import ChunkRecord, Embedder, QueryHit, SyncStats, VectorIndex

# Over-fetch factor so per-note dedupe still yields up to `limit` distinct notes.
_QUERY_OVERFETCH = 4


# Semantic searches that may embed and query at the same time.
SEARCH_CONCURRENCY = 2


class SemanticSearchService:
    """Keeps the embedding index in sync and answers semantic queries."""

    def __init__(
        self,
        client: JoplinClient,
        embedder: Embedder,
        index: VectorIndex,
        settings: Settings,
    ) -> None:
        self._client = client
        self._embedder = embedder
        self._index = index
        self._settings = settings
        self._lock = asyncio.Lock()
        # Query embedding runs on worker threads; a remote caller firing many
        # searches at once could otherwise tie up the model and the CPU.
        self._search_slots = asyncio.Semaphore(SEARCH_CONCURRENCY)

    async def sync(self, *, full: bool = False) -> SyncStats:
        """Incrementally re-embed changed notes (or rebuild everything)."""
        async with self._lock:
            return await self._sync_locked(full=full)

    async def prune(self) -> int:
        """Drop indexed notes that are hidden or gone, embedding nothing.

        The cheap half of a sync (one listing without bodies, no model). Returns
        how many notes left the index.
        """
        async with self._lock:
            indexed = await asyncio.to_thread(self._index.note_versions)
            if not indexed:
                return 0
            _, current = await self._visible_versions()
            gone = [note_id for note_id in indexed if note_id not in current]
            if gone:
                await asyncio.to_thread(self._index.delete_notes, gone)
            return len(gone)

    async def _visible_versions(self) -> tuple[NotebookScope, dict[str, str]]:
        """The scope as of now, and id → version for every note it lets through."""
        scope = await current_scope(self._client, self._settings)
        notes = await self._client.list_note_versions()
        versions = {
            note["id"]: str(note["updated_time"]) for note in notes if scope.allows_note(note)
        }
        return scope, versions

    async def _sync_locked(self, *, full: bool) -> SyncStats:
        # Ask Joplin first: if it is down, or the filter doesn't resolve, the
        # index is left exactly as it was (a full rebuild included).
        scope, current = await self._visible_versions()

        model = self._embedder.model_name
        if full or self._index.model_name != model:
            await asyncio.to_thread(self._index.reset, model)
            indexed: dict[str, str] = {}
        else:
            indexed = await asyncio.to_thread(self._index.note_versions)

        plan = diff_versions(current, indexed)

        # Drop before embedding: a note that is now hidden must leave the index
        # even if an embedding below fails.
        if plan.deleted_ids:
            await asyncio.to_thread(self._index.delete_notes, plan.deleted_ids)

        added = 0
        updated = 0
        for note_id in plan.changed_ids:
            if not await self._embed_note(note_id, current[note_id], scope):
                continue
            if note_id in indexed:
                updated += 1
            else:
                added += 1

        return SyncStats(
            added=added,
            updated=updated,
            deleted=len(plan.deleted_ids),
            total=len(current),
            model_name=model,
        )

    async def _embed_note(self, note_id: str, version: str, scope: NotebookScope) -> bool:
        """(Re)embed one note; False if it turned out to be hidden and was left out."""
        note = await self._client.get_note(note_id)

        # Drop any stale chunks first so a note that shrank leaves nothing behind.
        await asyncio.to_thread(self._index.delete_notes, [note_id])
        # The listing said this note was visible; it may have moved since. What is
        # embedded is decided by the notebook the text was actually read from.
        if not scope.allows_note(note):
            return False

        title = note.get("title", "")
        chunks = chunk_note(title, note.get("body", ""))
        if not chunks:
            return True

        embeddings = await asyncio.to_thread(self._embedder.embed_documents, chunks)
        records = [
            ChunkRecord(
                chunk_id=f"{note_id}::{i}",
                note_id=note_id,
                title=title,
                updated_time=version,
                chunk_index=i,
                text=text,
                embedding=embedding,
            )
            for i, (text, embedding) in enumerate(zip(chunks, embeddings, strict=True))
        ]
        await asyncio.to_thread(self._index.upsert, records)
        return True

    async def search(self, query: str, limit: int = 10) -> list[SemanticResult]:
        """Return up to ``limit`` notes most semantically similar to ``query``."""
        if self._settings.semantic_auto_sync:
            await self.sync()
        elif self._settings.notebook_filter_set:
            # No sync before this search, but the filter still has to hold now: a
            # note hidden since the last sync must not be answered from the index.
            await self.prune()

        async with self._search_slots:
            embedding = await asyncio.to_thread(self._embedder.embed_query, query)
            hits = await asyncio.to_thread(self._index.query, embedding, limit * _QUERY_OVERFETCH)

        best: dict[str, QueryHit] = {}
        for hit in hits:  # hits are ordered best-first
            best.setdefault(hit.note_id, hit)

        return [
            SemanticResult(
                id=hit.note_id,
                title=hit.title,
                excerpt=excerpt(hit.text),
                score=hit.score,
                chunk_index=hit.chunk_index,
            )
            for hit in list(best.values())[:limit]
        ]
