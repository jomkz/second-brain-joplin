"""Read-only MCP tools backed by the Joplin Data API."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastmcp import Context, FastMCP
from pydantic import Field

from ..context import app_context
from ..errors import JoplinError, JoplinNotFoundError, NotebookFilterError
from ..joplin_client import JsonDict
from ..models import (
    MAX_RECENT_DAYS,
    MAX_RECENT_LIMIT,
    MAX_SEARCH_LIMIT,
    READ_DEFAULT_CHARS,
    READ_MAX_CHARS,
    Note,
    Notebook,
    RecentNote,
    SearchResult,
    epoch_ms_to_iso,
    excerpt,
)
from ..scope import ID_PATTERN, NotebookScope, scope_of
from .annotations import READ_ONLY
from .failure import tool_error

SearchLimit = Annotated[int, Field(ge=1, le=MAX_SEARCH_LIMIT)]
NoteId = Annotated[str, Field(pattern=ID_PATTERN, description="A note's 32-character id.")]


def _build_overview(
    folders: list[JsonDict], notes_index: list[JsonDict], scope: NotebookScope
) -> list[Notebook]:
    """Assemble the tree of visible notebooks with per-notebook note counts.

    ``folders`` and ``notes_index`` are raw Joplin dicts. A notebook whose parent
    isn't shown (a root, or a visible notebook under one the filter hides) sits
    at the top of the tree, so a hidden parent's name never appears.
    """
    shown = [folder for folder in folders if scope.allows(folder["id"])]
    shown_ids = {folder["id"] for folder in shown}

    counts: dict[str, int] = {}
    for note in notes_index:
        parent = note.get("parent_id", "")
        counts[parent] = counts.get(parent, 0) + 1

    children_of: dict[str, list[JsonDict]] = {}
    for folder in shown:
        children_of.setdefault(folder.get("parent_id", ""), []).append(folder)

    def build(folder: JsonDict) -> Notebook:
        folder_id = folder["id"]
        return Notebook(
            id=folder_id,
            name=folder.get("title", ""),
            note_count=counts.get(folder_id, 0),
            children=[build(child) for child in children_of.get(folder_id, [])],
        )

    return [build(folder) for folder in shown if folder.get("parent_id", "") not in shown_ids]


def register(mcp: FastMCP) -> None:
    """Register the read tools on the given FastMCP server."""

    @mcp.tool(annotations=READ_ONLY)
    async def joplin_overview(ctx: Context) -> list[Notebook]:
        """List the Joplin notebooks as a tree with note counts."""
        app = app_context(ctx)
        try:
            folders = await app.client.get_folders()
            scope = scope_of(app.settings, folders)
            notes_index = await app.client.get_notes_index()
        except (JoplinError, NotebookFilterError) as exc:
            raise tool_error(exc) from exc
        return _build_overview(folders, notes_index, scope)

    @mcp.tool(annotations=READ_ONLY)
    async def joplin_search(
        ctx: Context, query: str, limit: SearchLimit = 10
    ) -> list[SearchResult]:
        """Search notes by keyword."""
        app = app_context(ctx)
        try:
            scope = await app.scope()
            hits = await app.client.search(query, limit, keep=scope.allows_note)
        except (JoplinError, NotebookFilterError) as exc:
            raise tool_error(exc) from exc
        return [
            SearchResult(
                id=hit["id"],
                title=hit.get("title", ""),
                excerpt=excerpt(hit.get("body", "")),
            )
            for hit in hits
        ]

    @mcp.tool(annotations=READ_ONLY)
    async def joplin_read(
        ctx: Context,
        note_id: NoteId,
        offset: Annotated[int, Field(ge=0)] = 0,
        max_chars: Annotated[int, Field(ge=1, le=READ_MAX_CHARS)] = READ_DEFAULT_CHARS,
    ) -> Note:
        """Read a note's markdown by its ID, a page at a time for long notes.

        Returns up to ``max_chars`` characters of the body starting at ``offset``.
        When ``next_offset`` is set, call again with ``offset=next_offset`` for the
        rest; ``total_chars`` is the whole body's length.
        """
        app = app_context(ctx)
        try:
            scope = await app.scope()
            note = await app.client.get_note(note_id)
            if not scope.allows_note(note):
                # The same answer as a note that doesn't exist.
                raise JoplinNotFoundError()
        except (JoplinError, NotebookFilterError) as exc:
            raise tool_error(exc) from exc
        body: str = note.get("body", "")
        end = offset + max_chars
        return Note(
            id=note["id"],
            title=note.get("title", ""),
            body=body[offset:end],
            parent_id=note.get("parent_id", ""),
            created_time=epoch_ms_to_iso(note["created_time"]),
            updated_time=epoch_ms_to_iso(note["updated_time"]),
            offset=offset,
            total_chars=len(body),
            next_offset=end if end < len(body) else None,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def joplin_recent(
        ctx: Context,
        days: Annotated[int, Field(ge=1, le=MAX_RECENT_DAYS)] = 7,
        limit: Annotated[int, Field(ge=1, le=MAX_RECENT_LIMIT)] = 20,
    ) -> list[RecentNote]:
        """List notes modified in the last N days, most recent first."""
        app = app_context(ctx)
        cutoff_ms = int((datetime.now(UTC) - timedelta(days=days)).timestamp() * 1000)
        try:
            scope = await app.scope()
            notes = await app.client.get_recent(limit, since_ms=cutoff_ms, keep=scope.allows_note)
        except (JoplinError, NotebookFilterError) as exc:
            raise tool_error(exc) from exc
        return [
            RecentNote(
                id=note["id"],
                title=note.get("title", ""),
                updated_time=epoch_ms_to_iso(note["updated_time"]),
            )
            for note in notes
        ]
