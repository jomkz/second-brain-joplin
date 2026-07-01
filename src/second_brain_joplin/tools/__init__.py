"""MCP tool registration."""

from fastmcp import FastMCP

from . import read, write


def register_tools(mcp: FastMCP) -> None:
    """Register all MCP tools on the given FastMCP server."""
    read.register(mcp)
    write.register(mcp)
