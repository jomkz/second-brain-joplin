"""MCP server construction and lifecycle."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

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


async def healthz(_request: Request) -> JSONResponse:
    """Say whether the server is up and whether Joplin answers, and nothing else.

    HTTP mode only (stdio has no routes). It is never behind sign-in, since FastMCP
    does not guard custom routes, so it reveals no note data, no version and no
    configuration: two booleans. 503 when Joplin is down, so a monitor sees it. It
    opens its own short-lived client, which keeps it independent of the MCP lifespan.
    """
    client = JoplinClient(Settings.from_env())
    try:
        joplin = await client.ping()
    finally:
        await client.aclose()
    return JSONResponse({"server": True, "joplin": joplin}, status_code=200 if joplin else 503)


def create_server() -> FastMCP:
    """Build the MCP server with every tool and the ``/healthz`` route."""
    server = FastMCP("second-brain-joplin", lifespan=lifespan)
    register_tools(server)
    server.custom_route("/healthz", methods=["GET"])(healthz)
    return server


mcp = create_server()
