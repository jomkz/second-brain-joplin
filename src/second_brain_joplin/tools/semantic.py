"""Semantic-search MCP tools backed by the embedding index.

Import-light: these tools reference only the app context and response models.
The optional ML/vector backends load lazily via ``app_context(ctx).semantic()``
when a tool is invoked, so the server (and the packaged-wheel smoke test) start
fine on a base install — invoking a semantic tool without the extra returns a
clear ``ToolError``.
"""

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError

from ..context import app_context
from ..errors import JoplinError, SemanticUnavailableError
from ..models import ReindexResult, SemanticResult


def register(mcp: FastMCP) -> None:
    """Register the semantic-search tools on the given FastMCP server."""

    @mcp.tool()
    async def joplin_semantic_search(
        ctx: Context, query: str, limit: int = 10
    ) -> list[SemanticResult]:
        """Find notes by meaning (semantic similarity), not just keywords."""
        try:
            service = app_context(ctx).semantic()
            return await service.search(query, limit)
        except (SemanticUnavailableError, JoplinError) as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    async def joplin_reindex(ctx: Context, full: bool = False) -> ReindexResult:
        """Sync the semantic index. ``full=True`` re-embeds every note from scratch."""
        try:
            service = app_context(ctx).semantic()
            stats = await service.sync(full=full)
        except (SemanticUnavailableError, JoplinError) as exc:
            raise ToolError(str(exc)) from exc
        return ReindexResult(
            added=stats.added,
            updated=stats.updated,
            deleted=stats.deleted,
            total=stats.total,
            model=stats.model_name,
        )
