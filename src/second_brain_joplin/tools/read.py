"""Read-only MCP tools backed by the Joplin Data API."""

from datetime import UTC, datetime, timedelta

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError

from ..context import app_context
from ..errors import JoplinError
from ..joplin_client import JsonDict
from ..models import Note, Notebook, RecentNote, SearchResult, epoch_ms_to_iso, excerpt


def _build_overview(folders: list[JsonDict], notes_index: list[JsonDict]) -> list[Notebook]:
    """Assemble a notebook tree with per-notebook note counts.

    ``folders`` and ``notes_index`` are raw Joplin dicts. Root folders have an
    empty ``parent_id``.
    """
    counts: dict[str, int] = {}
    for note in notes_index:
        parent = note.get("parent_id", "")
        counts[parent] = counts.get(parent, 0) + 1

    children_of: dict[str, list[JsonDict]] = {}
    for folder in folders:
        children_of.setdefault(folder.get("parent_id", ""), []).append(folder)

    def build(folder: JsonDict) -> Notebook:
        folder_id = folder["id"]
        return Notebook(
            id=folder_id,
            name=folder.get("title", ""),
            note_count=counts.get(folder_id, 0),
            children=[build(child) for child in children_of.get(folder_id, [])],
        )

    return [build(folder) for folder in children_of.get("", [])]


def register(mcp: FastMCP) -> None:
    """Register the read tools on the given FastMCP server."""

    @mcp.tool()
    async def joplin_overview(ctx: Context) -> list[Notebook]:
        """List all Joplin notebooks as a tree with note counts."""
        client = app_context(ctx).client
        try:
            folders = await client.get_folders()
            notes_index = await client.get_notes_index()
        except JoplinError as exc:
            raise ToolError(str(exc)) from exc
        return _build_overview(folders, notes_index)

    @mcp.tool()
    async def joplin_search(ctx: Context, query: str, limit: int = 10) -> list[SearchResult]:
        """Search notes by keyword across all notebooks."""
        client = app_context(ctx).client
        try:
            hits = await client.search(query, limit)
        except JoplinError as exc:
            raise ToolError(str(exc)) from exc
        return [
            SearchResult(
                id=hit["id"],
                title=hit.get("title", ""),
                excerpt=excerpt(hit.get("body", "")),
            )
            for hit in hits
        ]

    @mcp.tool()
    async def joplin_read(ctx: Context, note_id: str) -> Note:
        """Read the full markdown content of a note by its ID."""
        client = app_context(ctx).client
        try:
            note = await client.get_note(note_id)
        except JoplinError as exc:
            raise ToolError(str(exc)) from exc
        return Note(
            id=note["id"],
            title=note.get("title", ""),
            body=note.get("body", ""),
            parent_id=note.get("parent_id", ""),
            created_time=epoch_ms_to_iso(note["created_time"]),
            updated_time=epoch_ms_to_iso(note["updated_time"]),
        )

    @mcp.tool()
    async def joplin_recent(ctx: Context, days: int = 7, limit: int = 20) -> list[RecentNote]:
        """List notes modified in the last N days, most recent first."""
        client = app_context(ctx).client
        try:
            notes = await client.get_recent(limit)
        except JoplinError as exc:
            raise ToolError(str(exc)) from exc
        cutoff_ms = int((datetime.now(UTC) - timedelta(days=days)).timestamp() * 1000)
        return [
            RecentNote(
                id=note["id"],
                title=note.get("title", ""),
                updated_time=epoch_ms_to_iso(note["updated_time"]),
            )
            for note in notes
            if note.get("updated_time", 0) >= cutoff_ms
        ]
