"""Tests for the argparse CLI."""

from pathlib import Path
from typing import Any

import pytest

from second_brain_joplin import __version__, cli
from second_brain_joplin.cli import build_parser
from second_brain_joplin.remote import HttpOptions
from second_brain_joplin.server import mcp


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # setenv-then-delenv records each variable so monkeypatch removes it again
    # afterwards, including values an --env-file test loads.
    for name in ("SBJ_TRANSPORT", "SBJ_HOST", "SBJ_PORT", "SBJ_HTTP_PATH", "SBJ_PUBLIC_URL"):
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)
    # Keep the developer's own .env out of these tests.
    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: False)


@pytest.fixture
def http_calls(monkeypatch: pytest.MonkeyPatch) -> list[HttpOptions]:
    """Record run_http calls instead of starting a server."""
    calls: list[HttpOptions] = []
    monkeypatch.setattr(cli, "run_http", lambda _server, options: calls.append(options))
    return calls


def test_parser_parses_serve() -> None:
    args = build_parser().parse_args(["serve"])
    assert args.command == "serve"
    assert args.transport is None


def test_parser_no_command() -> None:
    args = build_parser().parse_args([])
    assert args.command is None


def test_parser_rejects_unknown_transport(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["serve", "--transport", "sse"])
    assert exc.value.code == 2


def test_version_flag_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_main_serve_defaults_to_stdio(
    monkeypatch: pytest.MonkeyPatch, http_calls: list[HttpOptions]
) -> None:
    called: dict[str, Any] = {}
    monkeypatch.setattr(mcp, "run", lambda *a, **k: called.setdefault("args", (a, k)))
    cli.main(["serve"])
    assert called["args"] == ((), {})
    assert http_calls == []


def test_main_without_command_prints_help(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(mcp, "run", lambda *a, **k: pytest.fail("mcp.run should not be called"))
    cli.main([])
    out = capsys.readouterr().out
    assert "serve" in out


def test_http_without_sign_in_or_no_auth_is_refused(
    capsys: pytest.CaptureFixture[str], http_calls: list[HttpOptions]
) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["serve", "--transport", "http"])
    assert exc.value.code == 2
    assert "sign-in" in capsys.readouterr().err
    assert http_calls == []


def test_http_no_auth_on_loopback_runs(http_calls: list[HttpOptions]) -> None:
    cli.main(["serve", "--transport", "http", "--no-auth", "--port", "9100"])
    assert http_calls == [HttpOptions(port=9100, no_auth=True)]


def test_transport_from_environment(
    monkeypatch: pytest.MonkeyPatch, http_calls: list[HttpOptions]
) -> None:
    monkeypatch.setenv("SBJ_TRANSPORT", "http")
    monkeypatch.setenv("SBJ_PORT", "9200")
    cli.main(["serve", "--no-auth"])
    assert http_calls == [HttpOptions(port=9200, no_auth=True)]


def test_bad_transport_in_environment_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SBJ_TRANSPORT", "carrier-pigeon")
    with pytest.raises(SystemExit) as exc:
        cli.main(["serve"])
    assert exc.value.code == 2
    assert "SBJ_TRANSPORT" in capsys.readouterr().err


@pytest.mark.parametrize(
    "flags",
    [["--host", "0.0.0.0"], ["--port", "9000"], ["--path", "/x"], ["--no-auth"]],
)
def test_http_flags_with_stdio_are_refused(
    flags: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["serve", *flags])
    assert exc.value.code == 2
    assert flags[0] in capsys.readouterr().err


def test_env_file_is_loaded_and_set_variables_win(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, http_calls: list[HttpOptions]
) -> None:
    env_file = tmp_path / "serve.env"
    env_file.write_text("SBJ_TRANSPORT=http\nSBJ_PORT=9300\nSBJ_HTTP_PATH=/from-file\n")
    monkeypatch.setenv("SBJ_HTTP_PATH", "/from-env")
    cli.main(["serve", "--env-file", str(env_file), "--no-auth"])
    assert http_calls == [HttpOptions(port=9300, path="/from-env", no_auth=True)]


def test_missing_env_file_is_an_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["serve", "--env-file", str(tmp_path / "absent.env")])
    assert exc.value.code == 2
    assert "absent.env" in capsys.readouterr().err
