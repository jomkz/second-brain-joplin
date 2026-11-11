"""Structured response models returned by the MCP tools.

Returning pydantic models (rather than plain dicts) gives FastMCP a rich output
schema for each tool automatically.
"""

from datetime import UTC, datetime

from pydantic import BaseModel

EXCERPT_LENGTH = 200

# Bounds on what one tool call may ask for. Claude caps a tool result near 150,000
# characters, so a single page of a note stays well under that.
MAX_SEARCH_LIMIT = 50
MAX_RECENT_LIMIT = 100
MAX_RECENT_DAYS = 3650
READ_DEFAULT_CHARS = 50_000
READ_MAX_CHARS = 100_000


def epoch_ms_to_iso(value: int) -> str:
    """Convert a Joplin epoch-millisecond timestamp to an ISO-8601 string."""
    return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat()


def excerpt(body: str) -> str:
    """Collapse whitespace and truncate ``body`` to a short single-line excerpt."""
    text = " ".join((body or "").split())
    if len(text) <= EXCERPT_LENGTH:
        return text
    return text[:EXCERPT_LENGTH].rstrip() + "…"


class Note(BaseModel):
    """A Joplin note, or one page of a long one.

    ``body`` holds the characters from ``offset``; ``total_chars`` is the whole
    body's length, and ``next_offset`` is where the next page starts, or None
    when this page reaches the end.
    """

    id: str
    title: str
    body: str
    parent_id: str
    created_time: str
    updated_time: str
    offset: int = 0
    total_chars: int = 0
    next_offset: int | None = None


class RecentNote(BaseModel):
    """A lightweight note entry for the recent-notes listing."""

    id: str
    title: str
    updated_time: str


class SearchResult(BaseModel):
    """A search hit: note identity plus a short body excerpt."""

    id: str
    title: str
    excerpt: str


class Notebook(BaseModel):
    """A notebook (Joplin folder) with its note count and nested children."""

    id: str
    name: str
    note_count: int
    children: list["Notebook"] = []


class SemanticResult(BaseModel):
    """A semantic-search hit: note identity, snippet, and similarity score."""

    id: str
    title: str
    excerpt: str
    score: float
    chunk_index: int


class ReindexResult(BaseModel):
    """Summary of a semantic index sync/rebuild."""

    added: int
    updated: int
    deleted: int
    total: int
    model: str
