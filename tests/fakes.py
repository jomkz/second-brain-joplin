"""In-memory fakes implementing the semantic Protocols, for tests.

Deterministic, dependency-free stand-ins for the real embedder and vector store
so the orchestration can be exercised without the optional ML/vector libs.
"""

import hashlib
import math

from second_brain_joplin.semantic.types import ChunkRecord, QueryHit

_DIM = 16


def _stable_hash(token: str) -> int:
    return int.from_bytes(hashlib.md5(token.encode()).digest()[:4], "big")


def _embed(text: str) -> list[float]:
    """Bag-of-tokens hashed into a fixed-dim, L2-normalized vector."""
    vec = [0.0] * _DIM
    for token in text.lower().split():
        vec[_stable_hash(token) % _DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


class FakeEmbedder:
    """Deterministic embedder over token hashes."""

    def __init__(self, model_name: str = "fake-model") -> None:
        self.model_name = model_name
        self.dim = _DIM
        self.doc_calls = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.doc_calls += 1
        return [_embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return _embed(text)


class FakeVectorIndex:
    """In-memory vector store keyed by chunk id."""

    def __init__(self) -> None:
        self.model_name = ""
        self._records: dict[str, ChunkRecord] = {}

    def note_versions(self) -> dict[str, str]:
        return {r.note_id: r.updated_time for r in self._records.values()}

    def upsert(self, records: list[ChunkRecord]) -> None:
        for record in records:
            self._records[record.chunk_id] = record

    def delete_notes(self, note_ids: list[str]) -> None:
        drop = set(note_ids)
        self._records = {cid: r for cid, r in self._records.items() if r.note_id not in drop}

    def query(self, embedding: list[float], k: int) -> list[QueryHit]:
        scored = [
            QueryHit(
                note_id=r.note_id,
                title=r.title,
                text=r.text,
                chunk_index=r.chunk_index,
                score=_cosine(embedding, r.embedding),
            )
            for r in self._records.values()
        ]
        scored.sort(key=lambda hit: hit.score, reverse=True)
        return scored[:k]

    def reset(self, model_name: str) -> None:
        self.model_name = model_name
        self._records = {}
