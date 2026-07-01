"""MCP server construction and lifecycle."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from .config import Settings
from .joplin_client import JoplinClient
from .tools import register_tools


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[JoplinClient]:
    """Own a single Joplin client for the server's lifetime.

    The yielded client is reachable from tools via ``ctx.lifespan_context``.
    """
    client = JoplinClient(Settings.from_env())
    try:
        yield client
    finally:
        await client.aclose()


mcp = FastMCP("second-brain-joplin", lifespan=lifespan)
register_tools(mcp)
