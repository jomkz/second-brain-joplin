"""MCP server construction and lifecycle."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from .config import Settings
from .context import AppContext
from .joplin_client import JoplinClient
from .tools import register_tools


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
    """Own the shared app context (Joplin client + settings) for the server's life.

    The yielded context is reachable from tools via ``ctx.lifespan_context``; the
    semantic service is built lazily on first use so startup never loads a model.
    """
    settings = Settings.from_env()
    client = JoplinClient(settings)
    try:
        yield AppContext(client=client, settings=settings)
    finally:
        await client.aclose()


mcp = FastMCP("second-brain-joplin", lifespan=lifespan)
register_tools(mcp)
