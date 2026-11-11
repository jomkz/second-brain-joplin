"""Tests for what HTTP mode logs (and never logs), the rate limit, and search slots."""

import asyncio
import logging
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
import respx
from fakes import FakeEmbedder, FakeVectorIndex
from fastmcp.server.auth import StaticTokenVerifier
from fastmcp.utilities.tests import ASGIServer, asgi_server
from mcp.shared.exceptions import MCPError

from second_brain_joplin.audit import QUIET_LOGGERS, configure_logging, rate_limit
from second_brain_joplin.config import Settings
from second_brain_joplin.remote import HttpOptions, http_app_kwargs
from second_brain_joplin.semantic.service import SEARCH_CONCURRENCY, SemanticSearchService
from second_brain_joplin.server import create_server

BASE_URL = "http://localhost:41184"
JOPLIN_TOKEN = "joplin-token-SECRET-1"
NOTE_TEXT = "note-body-SECRET-2"
QUERY = "query-SECRET-3"
TOKENS = {
    "john": {"client_id": "c", "scopes": [], "sub": "65598"},
    "other": {"client_id": "c", "scopes": [], "sub": "2"},
}


@pytest.fixture(autouse=True)
def _restore_loggers() -> Any:
    names = ("second_brain_joplin", *QUIET_LOGGERS)
    saved = {n: (logging.getLogger(n).level, list(logging.getLogger(n).handlers)) for n in names}
    yield
    for name, (level, handlers) in saved.items():
        logging.getLogger(name).setLevel(level)
        logging.getLogger(name).handlers[:] = handlers


@asynccontextmanager
async def serving(rate: int = 0) -> AsyncIterator[ASGIServer]:
    server = create_server(
        auth=StaticTokenVerifier(tokens=TOKENS),
        allowed_ids=frozenset({"65598", "2"}),
        rate_limit_per_minute=rate,
    )
    kwargs = http_app_kwargs(HttpOptions(public_url="https://joplin.example.com"))
    path = kwargs.pop("path")
    async with asgi_server(server, path=path, **kwargs) as running:
        yield running


def _mock_search() -> None:
    respx.get(f"{BASE_URL}/search").mock(
        return_value=httpx.Response(
            200, json={"items": [{"id": "n1", "title": "T", "body": NOTE_TEXT}], "has_more": False}
        )
    )


async def _search_as_john(running: ASGIServer) -> None:
    async with running.client(auth="john") as client:
        await client.call_tool("joplin_search", {"query": QUERY})


def test_configure_logging_quietens_url_loggers_and_is_idempotent() -> None:
    configure_logging()
    configure_logging()
    for name in QUIET_LOGGERS:
        assert logging.getLogger(name).level == logging.WARNING
    ours = [h for h in logging.getLogger("second_brain_joplin").handlers if getattr(h, "_sbj", 0)]
    assert len(ours) == 1


@respx.mock
async def test_unpinned_httpx_would_print_the_joplin_token(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The control: this is the leak configure_logging closes."""
    monkeypatch.setenv("JOPLIN_API_TOKEN", JOPLIN_TOKEN)
    _mock_search()
    caplog.set_level(logging.INFO)
    async with serving() as running:
        await _search_as_john(running)
    assert JOPLIN_TOKEN in caplog.text


@respx.mock
async def test_logs_hold_the_call_but_no_content_or_credentials(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("JOPLIN_API_TOKEN", JOPLIN_TOKEN)
    _mock_search()
    configure_logging()
    caplog.set_level(logging.INFO)
    async with serving() as running:
        await _search_as_john(running)
    text = caplog.text
    assert "tool=joplin_search caller=65598 outcome=ok" in text
    for secret in (JOPLIN_TOKEN, NOTE_TEXT, QUERY, "Bearer john"):
        assert secret not in text, secret


@respx.mock
async def test_failed_calls_are_logged_by_type_not_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    respx.get(f"{BASE_URL}/notes/{QUERY}").mock(return_value=httpx.Response(404))
    configure_logging()
    caplog.set_level(logging.INFO, logger="second_brain_joplin")
    async with serving() as running, running.client(auth="john") as client:
        result = await client.call_tool("joplin_read", {"note_id": QUERY}, raise_on_error=False)
    assert result.is_error
    audit = [r.getMessage() for r in caplog.records if r.name == "second_brain_joplin.audit"]
    assert audit and audit[0].startswith("tool=joplin_read caller=65598 outcome=error")
    assert QUERY not in " ".join(audit)


@respx.mock
async def test_rate_limit_is_per_caller() -> None:
    _mock_search()
    async with serving(rate=6) as running:  # bursts of 3 tool calls per caller
        outcomes = []
        async with running.client(auth="john") as client:
            assert await client.list_tools()  # listing is never counted
            for _ in range(5):
                try:
                    await client.call_tool("joplin_search", {"query": "q"})
                    outcomes.append("ok")
                except MCPError as exc:
                    assert "Rate limit exceeded for client: 65598" in str(exc)
                    outcomes.append("limited")
        async with running.client(auth="other") as client:  # a separate bucket
            other = await client.call_tool("joplin_search", {"query": "q"})
    assert outcomes == ["ok", "ok", "ok", "limited", "limited"]
    assert other.is_error is False


def test_rate_limit_needs_a_positive_rate() -> None:
    with pytest.raises(ValueError):
        rate_limit(0)


async def test_semantic_searches_are_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    active = 0
    peak = 0
    lock = threading.Lock()

    class SlowEmbedder(FakeEmbedder):
        def embed_query(self, text: str) -> list[float]:
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.05)
            with lock:
                active -= 1
            return super().embed_query(text)

    settings = Settings(semantic_auto_sync=False)
    service = SemanticSearchService(
        client=None,  # type: ignore[arg-type]  # auto-sync is off: Joplin is never called
        embedder=SlowEmbedder(),
        index=FakeVectorIndex(),
        settings=settings,
    )
    await asyncio.gather(*(service.search("q") for _ in range(6)))
    assert peak == SEARCH_CONCURRENCY
