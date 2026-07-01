"""Tests for the argparse CLI."""

import pytest

from second_brain_joplin import __version__, cli
from second_brain_joplin.cli import build_parser
from second_brain_joplin.server import mcp


def test_parser_parses_serve() -> None:
    args = build_parser().parse_args(["serve"])
    assert args.command == "serve"


def test_parser_no_command() -> None:
    args = build_parser().parse_args([])
    assert args.command is None


def test_version_flag_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_main_serve_invokes_mcp_run(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, bool] = {}
    monkeypatch.setattr(mcp, "run", lambda: called.setdefault("ran", True))
    cli.main(["serve"])
    assert called.get("ran") is True


def test_main_without_command_prints_help(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(mcp, "run", lambda: pytest.fail("mcp.run should not be called"))
    cli.main([])
    out = capsys.readouterr().out
    assert "serve" in out
