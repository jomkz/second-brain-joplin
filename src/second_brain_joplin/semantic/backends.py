"""Concrete embedders and vector stores backed by the optional extras.

This module is imported lazily — only from :meth:`AppContext.semantic` when a
semantic tool is actually invoked — and every heavy third-party import lives
*inside* a function/constructor. That keeps the base install and the packaged
wheel smoke test working without the extras, and lets a missing extra surface as
a friendly :class:`SemanticUnavailableError`.

Coverage-omitted (see ``[tool.coverage.run] omit`` in ``pyproject.toml``): it can
only run with the optional libs installed, which CI does not do. It is still
type-checked by mypy (the optional libs resolve to ``Any`` via
``ignore_missing_imports``), and exercised by the opt-in integration suite.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, cast

from ..config import Settings
from ..errors import SemanticUnavailableError
from .types import ChunkRecord, Embedder, QueryHit, VectorIndex

_FASTEMBED_DEFAULT = "BAAI/bge-small-en-v1.5"
_ST_DEFAULT = "BAAI/bge-m3"


def _install_hint(package: str, extra: str = "semantic") -> str:
    return (
        f"Semantic search needs the optional '{package}' dependency. Install it with "
        f'`pip install "second-brain-joplin[{extra}]"` (or the matching uvx/uv extra).'
    )


def build_embedder(settings: Settings) -> Embedder:
    """Construct the configured embedder, or raise ``SemanticUnavailableError``."""
    backend = settings.embedding_backend
    if backend == "fastembed":
        return _FastEmbedEmbedder(settings.embedding_model or _FASTEMBED_DEFAULT)
    if backend == "sentence-transformers":
        return _SentenceTransformerEmbedder(settings.embedding_model or _ST_DEFAULT)
    raise SemanticUnavailableError(
        f"Unknown SBJ_EMBEDDING_BACKEND {backend!r}; expected 'fastembed' or "
        "'sentence-transformers'."
    )


def build_vector_index(settings: Settings, model_name: str) -> VectorIndex:
    """Construct the configured vector store, or raise ``SemanticUnavailableError``."""
    store = settings.vector_store
    Path(settings.semantic_index_dir).mkdir(parents=True, exist_ok=True)
    if store == "sqlite-vec":
        return _SqliteVecIndex(settings.semantic_index_dir, model_name)
    if store == "chroma":
        return _ChromaVectorIndex(settings.semantic_index_dir, model_name)
    raise SemanticUnavailableError(
        f"Unknown SBJ_VECTOR_STORE {store!r}; expected 'sqlite-vec' or 'chroma'."
    )


class _FastEmbedEmbedder:
    def __init__(self, model_name: str) -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:  # pragma: no cover - env-dependent
            raise SemanticUnavailableError(_install_hint("fastembed")) from exc
        self.model_name = model_name
        self._model = TextEmbedding(model_name=model_name)
        probe = next(iter(self._model.embed(["probe"])))
        self.dim = len(probe)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(x) for x in vec] for vec in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        vec = next(iter(self._model.query_embed([text])))
        return [float(x) for x in vec]


class _SentenceTransformerEmbedder:
    def __init__(self, model_name: str) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - env-dependent
            raise SemanticUnavailableError(
                _install_hint("sentence-transformers", extra="semantic-st")
            ) from exc
        self.model_name = model_name
        self._model = SentenceTransformer(model_name)
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vecs = self._model.encode(texts, normalize_embeddings=True)
        return [[float(x) for x in vec] for vec in vecs]

    def embed_query(self, text: str) -> list[float]:
        vec = self._model.encode([text], normalize_embeddings=True)[0]
        return [float(x) for x in vec]


class _SqliteVecIndex:
    """Single-file sqlite-vec store: chunk metadata + a vec0 KNN table."""

    def __init__(self, index_dir: str, model_name: str) -> None:
        try:
            import sqlite_vec
        except ImportError as exc:  # pragma: no cover - env-dependent
            raise SemanticUnavailableError(_install_hint("sqlite-vec")) from exc
        self._target_model = model_name
        self._conn = sqlite3.connect(str(Path(index_dir) / "index.db"), check_same_thread=False)
        self._conn.enable_load_extension(True)
        sqlite_vec.load(self._conn)
        self._conn.enable_load_extension(False)
        self._serialize = sqlite_vec.serialize_float32
        self._conn.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT)")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS chunks("
            "rowid INTEGER PRIMARY KEY, chunk_id TEXT UNIQUE, note_id TEXT, "
            "updated_time TEXT, title TEXT, chunk_index INTEGER, text TEXT)"
        )
        self._conn.commit()

    @property
    def model_name(self) -> str:
        row = self._conn.execute("SELECT value FROM meta WHERE key = 'model'").fetchone()
        return cast(str, row[0]) if row else ""

    def _vec_table_ready(self) -> bool:
        row = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'vec_chunks'"
        ).fetchone()
        return row is not None

    def _ensure_vec_table(self, dim: int) -> None:
        if not self._vec_table_ready():
            self._conn.execute(
                f"CREATE VIRTUAL TABLE vec_chunks USING vec0(embedding float[{dim}])"
            )
            self._conn.commit()

    def note_versions(self) -> dict[str, str]:
        rows = self._conn.execute("SELECT note_id, updated_time FROM chunks").fetchall()
        return {note_id: updated for note_id, updated in rows}

    def upsert(self, records: list[ChunkRecord]) -> None:
        if not records:
            return
        self._ensure_vec_table(len(records[0].embedding))
        for record in records:
            cursor = self._conn.execute(
                "INSERT INTO chunks(chunk_id, note_id, updated_time, title, chunk_index, text) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (
                    record.chunk_id,
                    record.note_id,
                    record.updated_time,
                    record.title,
                    record.chunk_index,
                    record.text,
                ),
            )
            self._conn.execute(
                "INSERT INTO vec_chunks(rowid, embedding) VALUES(?, ?)",
                (cursor.lastrowid, self._serialize(record.embedding)),
            )
        self._conn.commit()

    def delete_notes(self, note_ids: list[str]) -> None:
        if not note_ids:
            return
        placeholders = ", ".join("?" for _ in note_ids)
        rows = self._conn.execute(
            f"SELECT rowid FROM chunks WHERE note_id IN ({placeholders})", note_ids
        ).fetchall()
        rowids = [r[0] for r in rows]
        self._conn.execute(f"DELETE FROM chunks WHERE note_id IN ({placeholders})", note_ids)
        if rowids and self._vec_table_ready():
            vec_placeholders = ", ".join("?" for _ in rowids)
            self._conn.execute(
                f"DELETE FROM vec_chunks WHERE rowid IN ({vec_placeholders})", rowids
            )
        self._conn.commit()

    def query(self, embedding: list[float], k: int) -> list[QueryHit]:
        if not self._vec_table_ready():
            return []
        rows = self._conn.execute(
            "SELECT c.note_id, c.title, c.text, c.chunk_index, v.distance "
            "FROM vec_chunks v JOIN chunks c ON c.rowid = v.rowid "
            "WHERE v.embedding MATCH ? AND k = ? ORDER BY v.distance",
            (self._serialize(embedding), k),
        ).fetchall()
        return [
            QueryHit(
                note_id=note_id,
                title=title,
                text=text,
                chunk_index=chunk_index,
                score=1.0 / (1.0 + float(distance)),
            )
            for note_id, title, text, chunk_index, distance in rows
        ]

    def reset(self, model_name: str) -> None:
        self._conn.execute("DROP TABLE IF EXISTS vec_chunks")
        self._conn.execute("DELETE FROM chunks")
        self._conn.execute(
            "INSERT INTO meta(key, value) VALUES('model', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (model_name,),
        )
        self._conn.commit()


class _ChromaVectorIndex:
    """Persistent Chroma collection keyed by chunk id."""

    _COLLECTION = "notes"

    def __init__(self, index_dir: str, model_name: str) -> None:
        try:
            import chromadb
        except ImportError as exc:  # pragma: no cover - env-dependent
            raise SemanticUnavailableError(
                _install_hint("chromadb", extra="semantic-chroma")
            ) from exc
        self._target_model = model_name
        self._client = chromadb.PersistentClient(path=str(Path(index_dir) / "chroma"))
        self._collection = self._client.get_or_create_collection(
            self._COLLECTION, metadata={"model": model_name}
        )

    @property
    def model_name(self) -> str:
        metadata = self._collection.metadata or {}
        return cast(str, metadata.get("model", ""))

    def note_versions(self) -> dict[str, str]:
        data = self._collection.get(include=["metadatas"])
        versions: dict[str, str] = {}
        for metadata in data.get("metadatas") or []:
            versions[str(metadata["note_id"])] = str(metadata["updated_time"])
        return versions

    def upsert(self, records: list[ChunkRecord]) -> None:
        if not records:
            return
        self._collection.upsert(
            ids=[r.chunk_id for r in records],
            embeddings=[r.embedding for r in records],
            documents=[r.text for r in records],
            metadatas=[
                {
                    "note_id": r.note_id,
                    "title": r.title,
                    "updated_time": r.updated_time,
                    "chunk_index": r.chunk_index,
                }
                for r in records
            ],
        )

    def delete_notes(self, note_ids: list[str]) -> None:
        if not note_ids:
            return
        self._collection.delete(where={"note_id": {"$in": note_ids}})

    def query(self, embedding: list[float], k: int) -> list[QueryHit]:
        result: dict[str, Any] = self._collection.query(
            query_embeddings=[embedding],
            n_results=k,
            include=["metadatas", "documents", "distances"],
        )
        metadatas = (result.get("metadatas") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        hits: list[QueryHit] = []
        for metadata, document, distance in zip(metadatas, documents, distances):
            hits.append(
                QueryHit(
                    note_id=str(metadata["note_id"]),
                    title=str(metadata["title"]),
                    text=str(document),
                    chunk_index=int(metadata["chunk_index"]),
                    score=1.0 / (1.0 + float(distance)),
                )
            )
        return hits

    def reset(self, model_name: str) -> None:
        try:
            self._client.delete_collection(self._COLLECTION)
        except Exception:  # noqa: BLE001 - collection may not exist yet
            pass
        self._collection = self._client.get_or_create_collection(
            self._COLLECTION, metadata={"model": model_name}
        )
