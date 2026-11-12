"""Semantic-search MCP tools backed by the embedding index.

Import-light: these tools reference only the app context and response models.
The optional ML/vector backends load lazily via ``app_context(ctx).semantic()``
when a tool is invoked, so the server (and the packaged-wheel smoke test) start
fine on a base install — invoking a semantic tool without the extra returns a
clear ``ToolError``.
"""

from typing import Annotated

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from ..context import app_context
from ..errors import JoplinError, NotebookFilterError, SemanticUnavailableError
from ..models import MAX_SEARCH_LIMIT, ReindexResult, SemanticResult
from .annotations import LOCAL_INDEX_WRITE, READ_ONLY
from .failure import tool_error


def register(mcp: FastMCP) -> None:
    """Register the semantic-search tools on the given FastMCP server."""

    # Read-only toward Joplin; with auto-sync on it may refresh the local index
    # first, which changes nothing a client can see except fresher results.
    @mcp.tool(annotations=READ_ONLY)
    async def joplin_semantic_search(
        ctx: Context, query: str, limit: Annotated[int, Field(ge=1, le=MAX_SEARCH_LIMIT)] = 10
    ) -> list[SemanticResult]:
        """Find notes by meaning (semantic similarity), not just keywords."""
        try:
            service = app_context(ctx).semantic()
            return await service.search(query, limit)
        except (SemanticUnavailableError, JoplinError, NotebookFilterError) as exc:
            raise tool_error(exc) from exc

    @mcp.tool(annotations=LOCAL_INDEX_WRITE)
    async def joplin_reindex(ctx: Context, full: bool = False) -> ReindexResult:
        """Sync the semantic index. ``full=True`` re-embeds every note from scratch."""
        app = app_context(ctx)
        if full and app.remote:
            raise ToolError(
                "A full rebuild can take longer than a remote tool call may run. Run "
                "`second-brain-joplin reindex --full` on the server's machine instead; "
                "incremental syncs (full=false) work here."
            )
        try:
            service = app.semantic()
            stats = await service.sync(full=full)
        except (SemanticUnavailableError, JoplinError, NotebookFilterError) as exc:
            raise tool_error(exc) from exc
        return ReindexResult(
            added=stats.added,
            updated=stats.updated,
            deleted=stats.deleted,
            total=stats.total,
            model=stats.model_name,
        )
