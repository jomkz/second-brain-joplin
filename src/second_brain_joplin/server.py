"""MCP server entry point."""

import os
from fastmcp import FastMCP

from .joplin_client import JoplinClient

mcp = FastMCP("second-brain-joplin")
_client: JoplinClient | None = None


def _get_client() -> JoplinClient:
    global _client
    if _client is None:
        token = os.environ.get("JOPLIN_API_TOKEN", "")
        base_url = os.environ.get("JOPLIN_BASE_URL", "http://localhost:41184")
        _client = JoplinClient(base_url=base_url, token=token)
    return _client


@mcp.tool()
async def joplin_overview() -> str:
    """List all Joplin notebooks with note counts."""
    raise NotImplementedError("Not yet implemented — tracked in GitHub issue T2")


@mcp.tool()
async def joplin_search(query: str) -> str:
    """Search notes by keyword across all notebooks."""
    raise NotImplementedError("Not yet implemented — tracked in GitHub issue T3")


@mcp.tool()
async def joplin_read(note_id: str) -> str:
    """Read the full content of a note by its ID."""
    raise NotImplementedError("Not yet implemented — tracked in GitHub issue T4")


@mcp.tool()
async def joplin_recent(days: int = 7) -> str:
    """List notes modified in the last N days."""
    raise NotImplementedError("Not yet implemented — tracked in GitHub issue T5")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
