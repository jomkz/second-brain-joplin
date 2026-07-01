"""MCP server entry point."""

import argparse
import os

from dotenv import load_dotenv
from fastmcp import FastMCP

from . import __version__
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


# All tools are stubbed for v0.1. They short-circuit with a "not implemented"
# payload and never reach the (also-stubbed) JoplinClient methods; real
# implementations land in v0.2 (GitHub issues #4–#8, #10).


@mcp.tool()
async def joplin_overview() -> dict:
    """List all Joplin notebooks with note counts."""
    return {"status": "not implemented", "tool": "joplin_overview", "issue": 5}


@mcp.tool()
async def joplin_search(query: str) -> dict:
    """Search notes by keyword across all notebooks."""
    return {"status": "not implemented", "tool": "joplin_search", "issue": 6}


@mcp.tool()
async def joplin_read(note_id: str) -> dict:
    """Read the full content of a note by its ID."""
    return {"status": "not implemented", "tool": "joplin_read", "issue": 7}


@mcp.tool()
async def joplin_recent(days: int = 7) -> dict:
    """List notes modified in the last N days."""
    return {"status": "not implemented", "tool": "joplin_recent", "issue": 8}


@mcp.tool()
async def joplin_create(title: str, body: str, notebook_id: str) -> dict:
    """Create a note in the given notebook (human-gated write)."""
    return {"status": "not implemented", "tool": "joplin_create", "issue": 10}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="second-brain-joplin",
        description="MCP server for Joplin knowledge bases.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("serve", help="Start the MCP server (stdio transport).")
    return parser


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "serve":
        mcp.run()
    else:
        parser.print_help()


if __name__ == "__main__":  # pragma: no cover
    main()
