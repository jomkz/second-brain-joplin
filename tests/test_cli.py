"""Tests for the argparse CLI."""

import pytest

from second_brain_joplin import __version__, cli
from second_brain_joplin.cli import build_parser


def test_parser_parses_serve():
    args = build_parser().parse_args(["serve"])
    assert args.command == "serve"


def test_parser_no_command():
    args = build_parser().parse_args([])
    assert args.command is None


def test_version_flag_prints_version(capsys):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_main_serve_invokes_mcp_run(monkeypatch):
    called = {}
    monkeypatch.setattr(cli.mcp, "run", lambda: called.setdefault("ran", True))
    cli.main(["serve"])
    assert called.get("ran") is True


def test_main_without_command_prints_help(monkeypatch, capsys):
    monkeypatch.setattr(cli.mcp, "run", lambda: pytest.fail("mcp.run should not be called"))
    cli.main([])
    out = capsys.readouterr().out
    assert "serve" in out
