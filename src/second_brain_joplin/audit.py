"""What HTTP mode logs, and what it never logs.

A long-running server needs a record of who called what, and that record must
never hold note content or credentials. Each tool call logs one line: the tool,
the caller's GitHub id, the outcome and the duration. Never arguments (a search
query is note content), never results, never tokens.

Two leaks are closed by configuration rather than code:

- **httpx request logging.** The Joplin API token rides in the URL's query string
  (Joplin's API takes it no other way), so httpx's INFO line for each request would
  print it. The HTTP client loggers are pinned to WARNING.
- **uvicorn's access log.** The OAuth callback URL carries the authorization code
  in its query string. The access log is off (see ``remote.run_http``).
"""

import logging
import sys
import time
from typing import Any

from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.server.middleware.rate_limiting import RateLimitingMiddleware

logger = logging.getLogger("second_brain_joplin.audit")

# Loggers that would print request URLs, and with them the Joplin token.
QUIET_LOGGERS = ("httpx", "httpcore", "httpx2", "httpcore2")
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
ANONYMOUS = "anonymous"


def caller_id(_context: MiddlewareContext[Any] | None = None) -> str:
    """The caller's GitHub user id, or ``anonymous`` with no sign-in."""
    token = get_access_token()
    if token is None:
        return ANONYMOUS
    user_id = token.claims.get("sub")
    return user_id if isinstance(user_id, str) and user_id else ANONYMOUS


class AuditMiddleware(Middleware):
    """Log one line per tool call: tool, caller, outcome, duration. Nothing else."""

    async def on_call_tool(
        self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]
    ) -> Any:
        tool = getattr(context.message, "name", "?")
        who = caller_id(context)
        started = time.perf_counter()
        try:
            result = await call_next(context)
        except Exception as exc:
            logger.info(
                "tool=%s caller=%s outcome=error:%s ms=%d",
                tool,
                who,
                type(exc).__name__,
                (time.perf_counter() - started) * 1000,
            )
            raise
        outcome = "error" if getattr(result, "is_error", False) else "ok"
        logger.info(
            "tool=%s caller=%s outcome=%s ms=%d",
            tool,
            who,
            outcome,
            (time.perf_counter() - started) * 1000,
        )
        return result


class ToolCallRateLimit(RateLimitingMiddleware):
    """FastMCP's token-bucket limiter, counting tool calls only.

    The stock middleware counts every MCP request, and one tool call from a
    client brings protocol requests with it (discovery, ``tools/list``), so a
    "60 a minute" limit would really mean a third of that. Listing and discovery
    are cheap; tool calls are what reach Joplin and the embedding model.
    """

    async def on_request(
        self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]
    ) -> Any:
        return await call_next(context)

    async def on_call_tool(
        self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]
    ) -> Any:
        return await super().on_request(context, call_next)


def rate_limit(per_minute: int) -> ToolCallRateLimit:
    """A per-caller token bucket of tool calls: ``per_minute`` sustained, bursts of half.

    Keyed by GitHub id (FastMCP's default is one bucket shared by every caller).
    """
    if per_minute < 1:
        raise ValueError("per_minute must be at least 1")
    return ToolCallRateLimit(
        max_requests_per_second=per_minute / 60,
        burst_capacity=max(1, per_minute // 2),
        get_client_id=caller_id,
    )


def configure_logging(level: int = logging.INFO) -> None:
    """Logging for HTTP mode: this package's lines on stderr, URL loggers quiet.

    Idempotent: calling it twice adds no second handler.
    """
    package = logging.getLogger("second_brain_joplin")
    package.setLevel(level)
    if not any(getattr(h, "_sbj", False) for h in package.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        handler._sbj = True  # type: ignore[attr-defined]
        package.addHandler(handler)
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
