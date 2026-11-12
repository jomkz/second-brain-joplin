"""In-memory fakes for tests: the semantic Protocols, and Joplin's Data API.

Deterministic, dependency-free stand-ins for the real embedder and vector store
so the orchestration can be exercised without the optional ML/vector libs, and
a small Joplin (notebooks, notes, search, paging) served through respx.
"""

import hashlib
import math
import re
from collections.abc import Callable
from typing import Any

import httpx
import respx

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

    def stored_text(self) -> str:
        """Everything a reader of the index could find in it: titles and chunk text."""
        return "\n".join(f"{r.title}\n{r.text}" for r in self._records.values())

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


class FakeJoplin:
    """An in-memory Joplin Data API behind respx: notebooks, notes, search, paging.

    Mirrors what the real API was seen to do (Joplin 3.7): ``/folders`` is a flat
    paginated list carrying ``parent_id``, listings honour ``fields``, ``page`` and
    ``order_by=updated_time``, and a missing note answers 404. Ids are 32
    hexadecimal characters, handed out in order. Call :meth:`install` inside a
    ``respx.mock`` block.
    """

    def __init__(self, base_url: str = "http://localhost:41184", page_size: int = 100) -> None:
        self.base_url = base_url
        self.page_size = page_size
        self.folders: dict[str, dict[str, Any]] = {}
        self.notes: dict[str, dict[str, Any]] = {}
        self.requests: list[str] = []  # the path of every request, in order
        self.down = False
        # Called with a note's id just before that note is served on its own, so
        # a test can change the vault between a listing and the read that follows.
        self.before_note: Callable[[str], None] | None = None
        self.note_status: int | None = None  # answer single-note reads with this
        self._next_id = 1

    def _new_id(self) -> str:
        new_id = f"{self._next_id:032x}"
        self._next_id += 1
        return new_id

    def notebook(self, title: str, parent: str = "") -> str:
        """Add a notebook (under ``parent``, an id) and return its id."""
        notebook_id = self._new_id()
        self.folders[notebook_id] = {"id": notebook_id, "title": title, "parent_id": parent}
        return notebook_id

    def note(self, title: str, body: str, notebook: str, updated_time: int = 100) -> str:
        """Add a note to the notebook with id ``notebook`` and return its id."""
        note_id = self._new_id()
        self.notes[note_id] = {
            "id": note_id,
            "title": title,
            "body": body,
            "parent_id": notebook,
            "created_time": 0,
            "updated_time": updated_time,
        }
        return note_id

    def move(self, note_id: str, notebook: str) -> None:
        """Move a note to another notebook, leaving its ``updated_time`` alone."""
        self.notes[note_id]["parent_id"] = notebook

    def count(self, path: str) -> int:
        """How many requests were made to exactly ``path``."""
        return self.requests.count(path)

    def install(self) -> None:
        base = re.escape(self.base_url)
        respx.get(f"{self.base_url}/folders").mock(side_effect=self._folders)
        respx.get(f"{self.base_url}/notes").mock(side_effect=self._notes)
        respx.get(f"{self.base_url}/search").mock(side_effect=self._search)
        respx.get(url__regex=rf"{base}/notes/[^/?]+").mock(side_effect=self._note)

    def _page(self, request: httpx.Request, rows: list[dict[str, Any]]) -> httpx.Response:
        self.requests.append(request.url.path)
        if self.down:
            raise httpx.ConnectError("Joplin is down")
        fields = request.url.params.get("fields", "id,parent_id,title").split(",")
        page = int(request.url.params.get("page", "1"))
        start = (page - 1) * self.page_size
        chunk = rows[start : start + self.page_size]
        return httpx.Response(
            200,
            json={
                "items": [{name: row[name] for name in fields} for row in chunk],
                "has_more": start + self.page_size < len(rows),
            },
        )

    def _folders(self, request: httpx.Request) -> httpx.Response:
        return self._page(request, list(self.folders.values()))

    def _notes(self, request: httpx.Request) -> httpx.Response:
        rows = list(self.notes.values())
        if request.url.params.get("order_by") == "updated_time":
            descending = request.url.params.get("order_dir") == "DESC"
            rows.sort(key=lambda note: note["updated_time"], reverse=descending)
        return self._page(request, rows)

    def _search(self, request: httpx.Request) -> httpx.Response:
        query = request.url.params.get("query", "").lower()
        rows = [
            note
            for note in self.notes.values()
            if query in note["title"].lower() or query in note["body"].lower()
        ]
        return self._page(request, rows)

    def _note(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request.url.path)
        if self.down:
            raise httpx.ConnectError("Joplin is down")
        note_id = request.url.path.rsplit("/", 1)[-1]
        if self.note_status is not None:
            return httpx.Response(self.note_status)
        if self.before_note is not None:
            self.before_note(note_id)
        note = self.notes.get(note_id)
        if note is None:
            return httpx.Response(404)
        return httpx.Response(200, json=note)
