"""Write MCP tools (human-gated). Stubbed until issue #10."""

from fastmcp import Context, FastMCP

from ..joplin_client import JsonDict


def register(mcp: FastMCP) -> None:
    """Register the write tools on the given FastMCP server."""

    @mcp.tool()
    async def joplin_create(ctx: Context, title: str, body: str, notebook_id: str) -> JsonDict:
        """Create a note in the given notebook (human-gated write).

        Not implemented yet: the human-in-the-loop confirmation flow (via
        ``ctx.elicit``) lands in issue #10. The ``ctx`` parameter is present now
        so that flow slots in without changing this signature.
        """
        return {"status": "not implemented", "tool": "joplin_create", "issue": 10}
