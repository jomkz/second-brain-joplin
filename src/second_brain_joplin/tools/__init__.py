"""MCP tool registration.

The read and semantic tools are always registered and are read-only toward
Joplin. The one write tool, ``joplin_create_note``, is registered only when the
operator has listed where notes may go (``SBJ_WRITE_NOTEBOOKS``); otherwise the
server is read-only and a client can't even see a write tool.
"""

from fastmcp import FastMCP

from . import read, semantic, write


def register_tools(mcp: FastMCP, *, writes: bool = False) -> None:
    """Register the MCP tools on the given FastMCP server; the write tool on request."""
    read.register(mcp)
    semantic.register(mcp)
    if writes:
        write.register(mcp)
