"""Structured response models returned by the MCP tools.

Returning pydantic models (rather than plain dicts) gives FastMCP a rich output
schema for each tool automatically.
"""

from datetime import UTC, datetime

from pydantic import BaseModel


def epoch_ms_to_iso(value: int) -> str:
    """Convert a Joplin epoch-millisecond timestamp to an ISO-8601 string."""
    return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat()


class Note(BaseModel):
    """A single Joplin note with its full body."""

    id: str
    title: str
    body: str
    parent_id: str
    created_time: str
    updated_time: str


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
