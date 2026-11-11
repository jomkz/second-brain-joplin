"""MCP tool registration.

Every tool is read-only toward Joplin. Note creation (``joplin_create``) comes back
with the human-gated write workflow (v0.5, issue #10); until then no write tool is
registered on any transport, so a remote client can't even see one.
"""

from fastmcp import FastMCP

from . import read, semantic


def register_tools(mcp: FastMCP) -> None:
    """Register all MCP tools on the given FastMCP server."""
    read.register(mcp)
    semantic.register(mcp)
