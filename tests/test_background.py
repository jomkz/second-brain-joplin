"""Tests for indexing outside the request path: background sync, the reindex CLI,
and the refusal of a full rebuild over HTTP."""

import asyncio
import logging
from typing import Any

import httpx
import pytest
import respx
from fakes import FakeEmbedder, FakeVectorIndex
from fastmcp import Client
from fastmcp.exceptions import ToolError

from second_brain_joplin import cli, server
from second_brain_joplin.background import sync_forever
from second_brain_joplin.context import AppContext
from second_brain_joplin.errors import (
    JoplinAPIError,
    NotebookFilterError,
    SemanticUnavailableError,
)
from second_brain_joplin.remote import HttpOptions, ServeConfigError, http_options, validate
from second_brain_joplin.semantic import backends
from second_brain_joplin.semantic.types import SyncStats
from second_brain_joplin.server import create_server, make_lifespan

BASE_URL = "http://localhost:41184"
STATS = SyncStats(added=1, updated=2, deleted=3, total=4, model_name="fake-model")


class FakeService:
    """Records sync calls; raises the queued errors first."""

    def __init__(self, errors: list[Exception] | None = None) -> None:
        self.calls = 0
        self.errors = list(errors or [])
        self.running = 0
        self.overlapped = False

    async def sync(self, *, full: bool = False) -> SyncStats:
        self.calls += 1
        self.running += 1
        self.overlapped = self.overlapped or self.running > 1
        try:
            await asyncio.sleep(0)
            if self.errors:
                raise self.errors.pop(0)
            return STATS
        finally:
            self.running -= 1


class FakeApp:
    def __init__(self, service: FakeService | Exception) -> None:
        self._service = service

    def semantic(self) -> FakeService:
        if isinstance(self._service, Exception):
            raise self._service
        return self._service


async def _run_for(app: Any, seconds: float, interval: float = 0.01) -> asyncio.Task[None]:
    task = asyncio.create_task(sync_forever(app, interval))
    await asyncio.sleep(seconds)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    return task


# -- the loop -----------------------------------------------------------------


async def test_syncs_at_start_and_then_on_the_interval(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="second_brain_joplin")
    service = FakeService()
    await _run_for(FakeApp(service), 0.08)
    assert service.calls >= 3
    assert not service.overlapped
    assert "added=1 updated=2 deleted=3 total=4" in caplog.text


async def test_a_failed_run_does_not_stop_the_loop(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="second_brain_joplin")
    service = FakeService(errors=[JoplinAPIError("Joplin said 500"), RuntimeError("note text")])
    await _run_for(FakeApp(service), 0.08)
    assert service.calls >= 3
    assert "Joplin said 500" in caplog.text
    assert "RuntimeError" in caplog.text
    assert "note text" not in caplog.text  # unknown errors are logged by type only


async def test_a_wrong_notebook_filter_skips_the_run_and_says_why(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="second_brain_joplin")
    error = NotebookFilterError("SBJ_NOTEBOOKS: no notebook is titled 'Wrok'")
    service = FakeService(errors=[error])
    await _run_for(FakeApp(service), 0.08)
    assert service.calls >= 3  # the loop goes on: the filter may be fixed in Joplin
    assert "skipped, the notebook filter is wrong: SBJ_NOTEBOOKS: no notebook" in caplog.text


async def test_missing_semantic_extra_stops_the_loop(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="second_brain_joplin")
    task = asyncio.create_task(sync_forever(FakeApp(SemanticUnavailableError("x")), 0.01))  # type: ignore[arg-type]
    await asyncio.wait_for(task, timeout=1)
    assert task.done() and not task.cancelled()
    assert "isn't installed" in caplog.text


# -- the lifespan -------------------------------------------------------------


async def test_lifespan_runs_and_cancels_the_sync_task(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    async def fake_sync_forever(app: AppContext, interval: float) -> None:
        seen.update(app=app, interval=interval)
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            seen["cancelled"] = True
            raise

    monkeypatch.setattr(server, "sync_forever", fake_sync_forever)
    lifespan = make_lifespan(remote=True, sync_interval_minutes=15)
    async with lifespan(create_server()) as app:
        await asyncio.sleep(0)
        assert app.remote is True
    assert seen["app"] is app
    assert seen["interval"] == 15 * 60
    assert seen["cancelled"] is True


async def test_no_interval_means_no_task(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "sync_forever", lambda *a: pytest.fail("must not start"))
    async with make_lifespan(remote=True, sync_interval_minutes=0)(create_server()) as app:
        assert app.remote is True


async def test_stdio_lifespan_is_local_with_no_task(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "sync_forever", lambda *a: pytest.fail("must not start"))
    async with server.lifespan(server.mcp) as app:
        assert app.remote is False


# -- the reindex tool over HTTP ----------------------------------------------


def _install_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    index = FakeVectorIndex()
    monkeypatch.setattr(backends, "build_embedder", lambda settings: FakeEmbedder())
    monkeypatch.setattr(backends, "build_vector_index", lambda settings, model_name: index)


def _mock_vault() -> None:
    respx.get(f"{BASE_URL}/notes").mock(
        return_value=httpx.Response(
            200, json={"items": [{"id": "a", "updated_time": 1}], "has_more": False}
        )
    )
    respx.get(f"{BASE_URL}/notes/a").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "a",
                "title": "A",
                "body": "alpha",
                "parent_id": "",
                "created_time": 0,
                "updated_time": 1,
            },
        )
    )


async def test_full_reindex_is_refused_remotely(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fakes(monkeypatch)
    with respx.mock(assert_all_called=False) as router:
        route = router.route(host="localhost")
        async with Client(create_server(remote=True)) as client:
            with pytest.raises(ToolError, match="reindex --full"):
                await client.call_tool("joplin_reindex", {"full": True})
    assert not route.called


@respx.mock
async def test_incremental_reindex_works_remotely(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fakes(monkeypatch)
    _mock_vault()
    async with Client(create_server(remote=True)) as client:
        result = await client.call_tool("joplin_reindex", {"full": False})
    assert result.data.added == 1


async def test_lifespan_is_entered_once_for_many_http_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stateless HTTP must not rebuild the app context (or restart sync) per request."""
    from fastmcp.utilities.tests import asgi_server

    from second_brain_joplin.remote import http_app_kwargs

    entries = 0
    real = AppContext

    def counting(*args: Any, **kwargs: Any) -> AppContext:
        nonlocal entries
        entries += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(server, "AppContext", counting)
    kwargs = http_app_kwargs(HttpOptions(no_auth=True))
    path = kwargs.pop("path")
    async with asgi_server(create_server(remote=True), path=path, **kwargs) as running:
        for _ in range(3):
            async with running.client() as client:
                await client.list_tools()
    assert entries == 1


# -- options and the CLI ------------------------------------------------------


def test_sync_interval_option() -> None:
    assert http_options(environ={}).sync_interval_minutes == 15
    assert http_options(environ={"SBJ_SYNC_INTERVAL_MINUTES": "0"}).sync_interval_minutes == 0
    with pytest.raises(ServeConfigError, match="SBJ_SYNC_INTERVAL_MINUTES"):
        validate(HttpOptions(no_auth=True, sync_interval_minutes=-5), auth_configured=False)


def test_serve_http_builds_a_remote_server_with_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    built: dict[str, Any] = {}
    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: False)
    monkeypatch.setattr(cli, "create_server", lambda **kwargs: built.update(kwargs) or "srv")
    monkeypatch.setattr(cli, "run_http", lambda server, options: None)
    monkeypatch.setattr(cli, "configure_logging", lambda: None)
    monkeypatch.setenv("SBJ_SYNC_INTERVAL_MINUTES", "30")
    cli.main(["serve", "--transport", "http", "--no-auth"])
    assert built["remote"] is True
    assert built["sync_interval_minutes"] == 30
    assert built["auth"] is None


@respx.mock
async def test_run_reindex_builds_the_index(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fakes(monkeypatch)
    _mock_vault()
    stats = await cli.run_reindex(full=True)
    assert (stats.added, stats.total, stats.model_name) == (1, 1, "fake-model")


def test_reindex_command_prints_counts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[bool] = []

    async def fake_run_reindex(full: bool) -> SyncStats:
        calls.append(full)
        return STATS

    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: False)
    monkeypatch.setattr(cli, "run_reindex", fake_run_reindex)
    cli.main(["reindex", "--full"])
    assert calls == [True]
    assert capsys.readouterr().out.strip() == (
        "added=1 updated=2 deleted=3 total=4 model=fake-model"
    )


@pytest.mark.parametrize(
    "error", [SemanticUnavailableError("install the [semantic] extra"), JoplinAPIError("HTTP 500")]
)
def test_reindex_command_errors_exit_1(
    error: Exception, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def failing(full: bool) -> SyncStats:
        raise error

    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: False)
    monkeypatch.setattr(cli, "run_reindex", failing)
    with pytest.raises(SystemExit) as exc:
        cli.main(["reindex"])
    assert exc.value.code == 1
    assert str(error) in capsys.readouterr().err
