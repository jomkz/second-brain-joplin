"""Streamable HTTP mode for ``serve``: options, start-up guardrails and the run call.

stdio stays the default. HTTP mode exists so a Claude custom connector, which calls
MCP servers from Anthropic's cloud, can reach this server through a tunnel. The
server itself binds to loopback by default; the tunnel (or a reverse proxy) is what
publishes it, under the public URL that sign-in needs as its base URL.

HTTP mode is **stateless with plain JSON responses**: every request stands alone,
so a restart never breaks a client's session, and no idle event stream is held
open for a proxy to cut. None of the tools sends server-initiated messages, which
is the only thing a stateful session would add.
"""

import ipaddress
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from fastmcp import FastMCP

DEFAULT_HOST = "127.0.0.1"
# 8765 is a common default for local tools (it is taken on the maintainer's
# workstation), so HTTP mode starts one step away from it.
DEFAULT_PORT = 8775
DEFAULT_PATH = "/mcp"


class ServeConfigError(Exception):
    """``serve`` was asked for a configuration it refuses to start with."""


@dataclass(frozen=True)
class HttpOptions:
    """Where and how the HTTP transport listens."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    path: str = DEFAULT_PATH
    public_url: str | None = None
    no_auth: bool = False

    @property
    def public_host(self) -> str | None:
        """The host name of ``public_url`` (``joplin.example.com``), if one is set."""
        if not self.public_url:
            return None
        return urlsplit(self.public_url).hostname


def is_loopback(host: str) -> bool:
    """Return True if ``host`` only ever answers on this machine."""
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def _env_port(environ: Mapping[str, str]) -> int | None:
    raw = environ.get("SBJ_PORT")
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        raise ServeConfigError(f"SBJ_PORT must be a number, got {raw!r}") from None


def http_options(
    *,
    host: str | None = None,
    port: int | None = None,
    path: str | None = None,
    public_url: str | None = None,
    no_auth: bool = False,
    environ: Mapping[str, str] | None = None,
) -> HttpOptions:
    """Build :class:`HttpOptions` from command-line values, falling back to ``SBJ_*``.

    A flag wins over its environment variable, which wins over the default.
    ``--no-auth`` has no environment variable on purpose: switching sign-in off
    must be visible on the command line.
    """
    env = os.environ if environ is None else environ
    env_port = _env_port(env)
    return HttpOptions(
        host=host or env.get("SBJ_HOST") or DEFAULT_HOST,
        port=port if port is not None else (env_port if env_port is not None else DEFAULT_PORT),
        path=path or env.get("SBJ_HTTP_PATH") or DEFAULT_PATH,
        public_url=(public_url or env.get("SBJ_PUBLIC_URL") or None),
        no_auth=no_auth,
    )


def _check_public_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ServeConfigError(f"the public URL must be an http(s) URL with a host, got {url!r}")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise ServeConfigError(
            f"the public URL must be the server's origin only (https://host), got {url!r}"
        )
    if parts.scheme == "http" and not is_loopback(parts.hostname):
        raise ServeConfigError(
            f"the public URL must use https unless it is a loopback address, got {url!r}"
        )


def validate(options: HttpOptions, *, auth_configured: bool) -> None:
    """Refuse configurations that would expose notes without sign-in.

    Without sign-in, HTTP mode starts only with an explicit ``--no-auth``, only on a
    loopback address, and only without a public URL: that is a local test, nothing
    more. A tunnel reaches a loopback server just as well as a public one, which is
    why loopback alone is not enough to skip sign-in.
    """
    if not 1 <= options.port <= 65535:
        raise ServeConfigError(f"the port must be between 1 and 65535, got {options.port}")
    if not options.path.startswith("/"):
        raise ServeConfigError(f"the endpoint path must start with '/', got {options.path!r}")
    if options.public_url:
        _check_public_url(options.public_url)
    if auth_configured:
        if options.no_auth:
            raise ServeConfigError("--no-auth was given but sign-in is configured; drop one")
        if not options.public_url:
            raise ServeConfigError(
                "sign-in needs the server's public URL (--public-url or SBJ_PUBLIC_URL): "
                "GitHub and Claude are sent back to it"
            )
        return
    if not options.no_auth:
        raise ServeConfigError(
            "HTTP mode needs GitHub sign-in configured (docs/remote-access.md). "
            "For a local test only, add --no-auth."
        )
    if not is_loopback(options.host):
        raise ServeConfigError(
            f"--no-auth is for local testing only: bind to a loopback address, not {options.host}"
        )
    if options.public_url:
        raise ServeConfigError("--no-auth can't be combined with a public URL")


def http_app_kwargs(options: HttpOptions) -> dict[str, Any]:
    """The keyword arguments shared by ``FastMCP.run`` and ``FastMCP.http_app``.

    Kept in one place so the tests build exactly the app that ``serve`` runs.
    """
    allowed_hosts = [options.public_host] if options.public_host else []
    return {
        "path": options.path,
        "stateless_http": True,
        "json_response": True,
        # Strict Host/Origin checking: loopback names plus the public host only. A
        # request naming any other Host is answered 421 before it reaches MCP.
        "host_origin_protection": True,
        "allowed_hosts": allowed_hosts,
    }


def run_http(server: FastMCP, options: HttpOptions) -> None:
    """Serve ``server`` over streamable HTTP until interrupted."""
    server.run(
        transport="http",
        host=options.host,
        port=options.port,
        show_banner=False,
        **http_app_kwargs(options),
    )
