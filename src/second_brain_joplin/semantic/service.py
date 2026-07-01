"""Orchestrates embedding sync and semantic search over Joplin notes.

Pure orchestration: it takes an already-built :class:`Embedder` and
:class:`VectorIndex` (see :mod:`.types`) by dependency injection and never
imports an optional dependency, so it is fully exercised in tests with in-memory
fakes. CPU-bound embedder/index calls are pushed to worker threads via
``asyncio.to_thread`` and serialized with a lock so concurrent tool calls cannot
corrupt the store.
"""

import asyncio

from ..config import Settings
from ..joplin_client import JoplinClient
from ..models import SemanticResult, excerpt
from .chunking import chunk_note
from .sync import diff_versions
from .types import ChunkRecord, Embedder, QueryHit, SyncStats, VectorIndex

# Over-fetch factor so per-note dedupe still yields up to `limit` distinct notes.
_QUERY_OVERFETCH = 4


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

    async def sync(self, *, full: bool = False) -> SyncStats:
        """Incrementally re-embed changed notes (or rebuild everything)."""
        async with self._lock:
            return await self._sync_locked(full=full)

    async def _sync_locked(self, *, full: bool) -> SyncStats:
        model = self._embedder.model_name
        if full or self._index.model_name != model:
            await asyncio.to_thread(self._index.reset, model)
            indexed: dict[str, str] = {}
        else:
            indexed = await asyncio.to_thread(self._index.note_versions)

        current_notes = await self._client.list_note_versions()
        current = {note["id"]: str(note["updated_time"]) for note in current_notes}
        plan = diff_versions(current, indexed)

        added = 0
        updated = 0
        for note_id in plan.changed_ids:
            await self._embed_note(note_id, current[note_id])
            if note_id in indexed:
                updated += 1
            else:
                added += 1

        if plan.deleted_ids:
            await asyncio.to_thread(self._index.delete_notes, plan.deleted_ids)

        return SyncStats(
            added=added,
            updated=updated,
            deleted=len(plan.deleted_ids),
            total=len(current),
            model_name=model,
        )

    async def _embed_note(self, note_id: str, version: str) -> None:
        note = await self._client.get_note(note_id)
        title = note.get("title", "")
        chunks = chunk_note(title, note.get("body", ""))

        # Drop any stale chunks first so a note that shrank leaves nothing behind.
        await asyncio.to_thread(self._index.delete_notes, [note_id])
        if not chunks:
            return

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

    async def search(self, query: str, limit: int = 10) -> list[SemanticResult]:
        """Return up to ``limit`` notes most semantically similar to ``query``."""
        if self._settings.semantic_auto_sync:
            await self.sync()

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
