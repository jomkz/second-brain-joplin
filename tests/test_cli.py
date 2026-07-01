"""Tests for the argparse CLI."""

import pytest

from second_brain_joplin import __version__
from second_brain_joplin.server import build_parser


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
