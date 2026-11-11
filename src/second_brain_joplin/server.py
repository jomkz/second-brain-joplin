"""MCP server construction and lifecycle."""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress

from fastmcp import FastMCP
from fastmcp.server.auth import AuthProvider
from fastmcp.server.middleware import AuthMiddleware, Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .audit import AuditMiddleware, rate_limit
from .auth import allowlist_check
from .background import sync_forever
from .config import Settings
from .context import AppContext
from .joplin_client import JoplinClient
from .tools import register_tools

Lifespan = Callable[[FastMCP], AbstractAsyncContextManager[AppContext]]


def make_lifespan(*, remote: bool = False, sync_interval_minutes: int = 0) -> Lifespan:
    """A lifespan owning the shared app context, plus HTTP mode's background sync.

    The yielded context is reachable from tools via ``ctx.lifespan_context``; the
    semantic service is built lazily on first use, so start-up never waits on a
    model. With ``sync_interval_minutes`` above 0 a background task keeps the index
    fresh (background.py) and is cancelled when the server stops.
    """

    @asynccontextmanager
    async def lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
        settings = Settings.from_env()
        client = JoplinClient(settings)
        app = AppContext(client=client, settings=settings, remote=remote)
        task = (
            asyncio.create_task(sync_forever(app, sync_interval_minutes * 60))
            if sync_interval_minutes > 0
            else None
        )
        try:
            yield app
        finally:
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            await client.aclose()

    return lifespan


# stdio: no background work, every tool allowed.
lifespan = make_lifespan()


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


def create_server(
    *,
    auth: AuthProvider | None = None,
    allowed_ids: frozenset[str] | None = None,
    rate_limit_per_minute: int = 0,
    remote: bool = False,
    sync_interval_minutes: int = 0,
) -> FastMCP:
    """Build the MCP server with every tool and the ``/healthz`` route.

    With ``auth`` (HTTP mode), ``allowed_ids`` adds the per-tool allowlist check as
    a second layer behind the token verifier. ``rate_limit_per_minute`` (0 = off)
    limits each caller. Every tool call is logged without its content (audit.py).
    ``remote`` and ``sync_interval_minutes`` are HTTP mode's: see make_lifespan.
    """
    if auth is not None and not allowed_ids:
        raise ValueError("a server with sign-in needs its allowed GitHub ids")
    middleware: list[Middleware] = []
    if rate_limit_per_minute:
        middleware.append(rate_limit(rate_limit_per_minute))
    if allowed_ids:
        middleware.append(AuthMiddleware(auth=allowlist_check(allowed_ids)))
    middleware.append(AuditMiddleware())
    server_lifespan = (
        make_lifespan(remote=remote, sync_interval_minutes=sync_interval_minutes)
        if remote or sync_interval_minutes
        else lifespan
    )
    server = FastMCP(
        "second-brain-joplin", lifespan=server_lifespan, auth=auth, middleware=middleware
    )
    register_tools(server)
    server.custom_route("/healthz", methods=["GET"])(healthz)
    return server


mcp = create_server()
