"""Tests for HTTP mode: options, start-up guardrails, and the app over real HTTP."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import httpx2
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.utilities.tests import ASGIServer, asgi_server

from second_brain_joplin.remote import (
    DEFAULT_PORT,
    HttpOptions,
    ServeConfigError,
    http_app_kwargs,
    http_options,
    is_loopback,
    run_http,
    validate,
)
from second_brain_joplin.server import create_server

BASE_URL = "http://localhost:41184"

# -- options ------------------------------------------------------------------


def test_defaults() -> None:
    options = http_options(environ={})
    assert options == HttpOptions(host="127.0.0.1", port=DEFAULT_PORT, path="/mcp")
    assert options.public_host is None


def test_environment_fills_in_and_flags_win() -> None:
    env = {
        "SBJ_HOST": "::1",
        "SBJ_PORT": "9001",
        "SBJ_HTTP_PATH": "/env",
        "SBJ_PUBLIC_URL": "https://joplin.example.com",
    }
    from_env = http_options(environ=env)
    assert from_env == HttpOptions(
        host="::1", port=9001, path="/env", public_url="https://joplin.example.com"
    )
    assert from_env.public_host == "joplin.example.com"
    from_flags = http_options(host="localhost", port=9002, path="/flag", environ=env)
    assert (from_flags.host, from_flags.port, from_flags.path) == ("localhost", 9002, "/flag")


def test_port_zero_flag_is_kept_not_replaced_by_default() -> None:
    assert http_options(port=0, environ={}).port == 0


def test_empty_environment_values_mean_unset() -> None:
    assert http_options(environ={"SBJ_PORT": "", "SBJ_PUBLIC_URL": ""}) == HttpOptions()


def test_non_numeric_port_in_environment() -> None:
    with pytest.raises(ServeConfigError, match="SBJ_PORT"):
        http_options(environ={"SBJ_PORT": "eighty"})


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", True),
        ("127.8.9.10", True),
        ("::1", True),
        ("[::1]", True),
        ("localhost", True),
        ("LOCALHOST", True),
        ("0.0.0.0", False),
        ("::", False),
        ("10.42.20.11", False),
        ("mercury", False),
    ],
)
def test_is_loopback(host: str, expected: bool) -> None:
    assert is_loopback(host) is expected


# -- guardrails ---------------------------------------------------------------


def test_http_without_sign_in_needs_no_auth() -> None:
    with pytest.raises(ServeConfigError, match="--no-auth"):
        validate(HttpOptions(), auth_configured=False)


def test_no_auth_on_loopback_is_allowed() -> None:
    validate(HttpOptions(no_auth=True), auth_configured=False)
    validate(HttpOptions(host="::1", no_auth=True), auth_configured=False)


@pytest.mark.parametrize("host", ["0.0.0.0", "10.42.20.11", "::"])
def test_no_auth_off_loopback_is_refused(host: str) -> None:
    with pytest.raises(ServeConfigError, match="loopback"):
        validate(HttpOptions(host=host, no_auth=True), auth_configured=False)


def test_no_auth_with_public_url_is_refused() -> None:
    options = HttpOptions(no_auth=True, public_url="http://127.0.0.1:8775")
    with pytest.raises(ServeConfigError, match="public URL"):
        validate(options, auth_configured=False)


def test_no_auth_with_sign_in_configured_is_refused() -> None:
    with pytest.raises(ServeConfigError, match="drop one"):
        validate(HttpOptions(no_auth=True), auth_configured=True)


def test_sign_in_allows_any_host() -> None:
    options = HttpOptions(host="0.0.0.0", public_url="https://joplin.example.com")
    validate(options, auth_configured=True)


@pytest.mark.parametrize(
    "url",
    [
        "joplin.example.com",  # no scheme
        "ftp://joplin.example.com",
        "https://",
        "https://joplin.example.com/mcp",  # a path: the origin only
        "https://joplin.example.com/?x=1",
        "http://joplin.example.com",  # plain http off loopback
    ],
)
def test_bad_public_urls(url: str) -> None:
    with pytest.raises(ServeConfigError, match="public URL"):
        validate(HttpOptions(public_url=url), auth_configured=True)


def test_good_public_urls() -> None:
    for url in ("https://joplin.example.com", "https://joplin.example.com/", "http://127.0.0.1:9"):
        validate(HttpOptions(public_url=url), auth_configured=True)


@pytest.mark.parametrize("port", [0, -1, 65536])
def test_port_out_of_range(port: int) -> None:
    with pytest.raises(ServeConfigError, match="port"):
        validate(HttpOptions(port=port, no_auth=True), auth_configured=False)


def test_path_must_start_with_slash() -> None:
    with pytest.raises(ServeConfigError, match="path"):
        validate(HttpOptions(path="mcp", no_auth=True), auth_configured=False)


# -- the app ------------------------------------------------------------------


def test_app_kwargs_are_stateless_json_with_strict_hosts() -> None:
    kwargs = http_app_kwargs(HttpOptions(public_url="https://joplin.example.com"))
    assert kwargs == {
        "path": "/mcp",
        "stateless_http": True,
        "json_response": True,
        "host_origin_protection": True,
        "allowed_hosts": ["joplin.example.com"],
    }
    assert http_app_kwargs(HttpOptions())["allowed_hosts"] == []


def test_run_http_passes_the_same_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    server = create_server()
    seen: dict[str, Any] = {}
    monkeypatch.setattr(server, "run", lambda **kwargs: seen.update(kwargs))
    options = HttpOptions(host="::1", port=9400, no_auth=True)
    run_http(server, options)
    assert seen == {
        "transport": "http",
        "host": "::1",
        "port": 9400,
        "show_banner": False,
        **http_app_kwargs(options),
    }


@asynccontextmanager
async def serving(options: HttpOptions, server: FastMCP | None = None) -> AsyncIterator[ASGIServer]:
    kwargs = http_app_kwargs(options)
    path = kwargs.pop("path")
    async with asgi_server(server or create_server(), path=path, **kwargs) as running:
        yield running


def raw_client(running: ASGIServer, host: str | None = None) -> httpx2.AsyncClient:
    """A plain HTTP client into the app, connected as uvicorn would be: on 127.0.0.1.

    ``host`` changes only the Host header. (The ASGI ``server`` address comes from
    the base URL, and the guard always trusts the address it is bound to, so a test
    that put another name there would be testing nothing.)
    """
    return httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=running.app),
        base_url="http://127.0.0.1",
        headers={"Host": host} if host else None,
    )


@respx.mock
async def test_round_trip_over_http() -> None:
    respx.get(f"{BASE_URL}/folders").mock(
        return_value=httpx.Response(
            200, json={"items": [{"id": "f1", "title": "Inbox", "parent_id": ""}]}
        )
    )
    respx.get(f"{BASE_URL}/notes").mock(
        return_value=httpx.Response(200, json={"items": [{"id": "n1", "parent_id": "f1"}]})
    )
    async with serving(HttpOptions(no_auth=True)) as running, running.client() as client:
        names = {tool.name for tool in await client.list_tools()}
        result = await client.call_tool("joplin_overview", {})
    assert "joplin_overview" in names
    assert result.is_error is False


@respx.mock
async def test_stateless_requests_need_no_session() -> None:
    """Two separate clients, no shared session: each request stands alone."""
    async with serving(HttpOptions(no_auth=True)) as running:
        for _ in range(2):
            async with running.client() as client:
                assert await client.list_tools()


@respx.mock
async def test_healthz_up() -> None:
    respx.get(f"{BASE_URL}/ping").mock(return_value=httpx.Response(200, text="JoplinClipperServer"))
    async with serving(HttpOptions(no_auth=True)) as running, raw_client(running) as http:
        response = await http.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"server": True, "joplin": True}


@pytest.mark.parametrize(
    "failure",
    [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")],
    ids=["refused", "timeout"],
)
@respx.mock
async def test_healthz_joplin_down(failure: Exception) -> None:
    respx.get(f"{BASE_URL}/ping").mock(side_effect=failure)
    async with serving(HttpOptions(no_auth=True)) as running, raw_client(running) as http:
        response = await http.get("/healthz")
    assert response.status_code == 503
    assert response.json() == {"server": True, "joplin": False}


@respx.mock
async def test_unknown_host_header_is_refused() -> None:
    respx.get(f"{BASE_URL}/ping").mock(return_value=httpx.Response(200, text="JoplinClipperServer"))
    options = HttpOptions(public_url="https://joplin.example.com")
    async with serving(options) as running:
        async with raw_client(running, "evil.example") as http:
            assert (await http.get("/healthz")).status_code == 421
        async with raw_client(running, "joplin.example.com") as http:
            assert (await http.get("/healthz")).status_code == 200
