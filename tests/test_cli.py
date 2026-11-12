"""Tests for the argparse CLI."""

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import respx
from fakes import FakeEmbedder, FakeJoplin, FakeVectorIndex

from second_brain_joplin import __version__, cli
from second_brain_joplin.cli import build_parser
from second_brain_joplin.remote import HttpOptions
from second_brain_joplin.scope import NotebookScope
from second_brain_joplin.semantic import backends
from second_brain_joplin.server import mcp


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # setenv-then-delenv records each variable so monkeypatch removes it again
    # afterwards, including values an --env-file test loads.
    for name in (
        "SBJ_TRANSPORT",
        "SBJ_HOST",
        "SBJ_PORT",
        "SBJ_HTTP_PATH",
        "SBJ_PUBLIC_URL",
        "SBJ_GITHUB_CLIENT_ID",
        "SBJ_GITHUB_CLIENT_SECRET",
        "SBJ_JWT_SIGNING_KEY",
        "SBJ_ALLOWED_GITHUB_IDS",
        "SBJ_OAUTH_REDIRECT_URIS",
        "SBJ_NOTEBOOKS",
        "SBJ_EXCLUDE_NOTEBOOKS",
    ):
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


SIGN_IN_ENV = {
    "SBJ_GITHUB_CLIENT_ID": "id",
    "SBJ_GITHUB_CLIENT_SECRET": "secret",
    "SBJ_JWT_SIGNING_KEY": "k" * 40,
    "SBJ_ALLOWED_GITHUB_IDS": "65598",
}


@pytest.fixture
def sign_in_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in SIGN_IN_ENV.items():
        monkeypatch.setenv(name, value)


def test_http_with_sign_in_builds_an_authed_server(
    sign_in_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastmcp.server.auth import StaticTokenVerifier

    built: dict[str, Any] = {}
    fake_auth = StaticTokenVerifier(tokens={})

    def fake_build_auth(settings: Any, public_url: str) -> StaticTokenVerifier:
        built.update(ids=settings.allowed_ids, public_url=public_url)
        return fake_auth

    servers: list[Any] = []
    monkeypatch.setattr(cli, "build_auth", fake_build_auth)
    monkeypatch.setattr(cli, "run_http", lambda server, options: servers.append((server, options)))
    cli.main(["serve", "--transport", "http", "--public-url", "https://joplin.example.com"])
    assert built == {"ids": frozenset({"65598"}), "public_url": "https://joplin.example.com"}
    server, options = servers[0]
    assert server.auth is fake_auth
    assert options.public_url == "https://joplin.example.com"


def test_http_with_sign_in_but_no_public_url_is_refused(
    sign_in_env: None, capsys: pytest.CaptureFixture[str], http_calls: list[HttpOptions]
) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["serve", "--transport", "http"])
    assert exc.value.code == 2
    assert "public URL" in capsys.readouterr().err
    assert http_calls == []


def test_partial_sign_in_is_refused_without_printing_secrets(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SBJ_GITHUB_CLIENT_SECRET", "secret-value-123")
    with pytest.raises(SystemExit):
        cli.main(["serve", "--transport", "http", "--public-url", "https://joplin.example.com"])
    err = capsys.readouterr().err
    assert "SBJ_GITHUB_CLIENT_ID" in err
    assert "secret-value-123" not in err


# -- the notebook filter: the `notebooks` command and the start-up check ----------


@pytest.fixture
def joplin() -> Iterator[FakeJoplin]:
    """Work ─ Projects and Journal, with 2, 1 and 3 notes."""
    with respx.mock:
        fake = FakeJoplin()
        work = fake.notebook("Work")
        projects = fake.notebook("Projects", parent=work)
        journal = fake.notebook("Journal")
        for notebook, notes in ((work, 2), (projects, 1), (journal, 3)):
            for n in range(notes):
                fake.note(f"Note {n}", "body text", notebook)
        fake.install()
        yield fake


def _ids_by_title(joplin: FakeJoplin) -> dict[str, str]:
    return {folder["title"]: folder["id"] for folder in joplin.folders.values()}


def test_notebooks_command_lists_ids_counts_and_visibility(
    joplin: FakeJoplin, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ids = _ids_by_title(joplin)
    monkeypatch.setenv("SBJ_EXCLUDE_NOTEBOOKS", "Journal")
    cli.main(["notebooks"])
    assert capsys.readouterr().out.splitlines() == [
        "Notebook filter: 2 of 3 notebooks visible.",
        f"hidden   {ids['Journal']}  Journal (3)",
        f"visible  {ids['Work']}  Work (2)",
        f"visible  {ids['Projects']}    Projects (1)",
    ]


def test_notebooks_command_without_a_filter_says_everything_is_visible(
    joplin: FakeJoplin, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(["notebooks"])
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "No notebook filter is set: all 3 notebooks are visible."
    assert [line.split()[0] for line in lines[1:]] == ["visible"] * 3


def test_notebooks_command_with_a_wrong_filter_shows_the_ids_and_the_reason(
    joplin: FakeJoplin, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ids = _ids_by_title(joplin)
    monkeypatch.setenv("SBJ_NOTEBOOKS", "Wrok")
    with pytest.raises(SystemExit) as exc:
        cli.main(["notebooks"])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "error: SBJ_NOTEBOOKS: no notebook is titled 'Wrok'" in captured.err
    # The tree still prints, unmarked: its ids are what fixes the filter.
    assert captured.out.splitlines()[1] == f"?        {ids['Work']}  Work (2)"
    assert "visible" not in captured.out and "hidden" not in captured.out


def test_notebooks_command_with_joplin_down_exits_1(
    joplin: FakeJoplin, capsys: pytest.CaptureFixture[str]
) -> None:
    joplin.down = True
    with pytest.raises(SystemExit) as exc:
        cli.main(["notebooks"])
    assert exc.value.code == 1
    assert "unreachable" in capsys.readouterr().err


def test_notebook_lines_puts_a_notebook_with_an_unknown_parent_at_the_top() -> None:
    folders = [{"id": "b" * 32, "title": "Stray", "parent_id": "9" * 32}]
    lines = cli.notebook_lines(folders, [], NotebookScope())
    assert lines == [f"visible  {'b' * 32}  Stray (0)"]


def test_serve_refuses_to_start_with_a_wrong_filter(
    joplin: FakeJoplin,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    http_calls: list[HttpOptions],
) -> None:
    monkeypatch.setattr(mcp, "run", lambda *a, **k: pytest.fail("the server must not start"))
    monkeypatch.setenv("SBJ_EXCLUDE_NOTEBOOKS", "Jurnal")
    for argv in (["serve"], ["serve", "--transport", "http", "--no-auth"]):
        with pytest.raises(SystemExit) as exc:
            cli.main(argv)
        assert exc.value.code == 2
        assert "SBJ_EXCLUDE_NOTEBOOKS: no notebook is titled 'Jurnal'" in capsys.readouterr().err
    assert http_calls == []


def test_serve_starts_with_a_good_filter(
    joplin: FakeJoplin, monkeypatch: pytest.MonkeyPatch, http_calls: list[HttpOptions]
) -> None:
    started: list[str] = []
    monkeypatch.setattr(mcp, "run", lambda *a, **k: started.append("stdio"))
    monkeypatch.setenv("SBJ_NOTEBOOKS", "Work")
    cli.main(["serve"])
    cli.main(["serve", "--transport", "http", "--no-auth"])
    assert started == ["stdio"]
    assert len(http_calls) == 1


def test_serve_starts_when_joplin_is_down_and_says_the_filter_is_unchecked(
    joplin: FakeJoplin,
    monkeypatch: pytest.MonkeyPatch,
    http_calls: list[HttpOptions],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="second_brain_joplin")
    joplin.down = True
    monkeypatch.setenv("SBJ_NOTEBOOKS", "Work")
    cli.main(["serve", "--transport", "http", "--no-auth"])
    assert len(http_calls) == 1
    assert "couldn't be checked at start-up" in caplog.text


def test_serve_without_a_filter_does_not_ask_joplin(
    joplin: FakeJoplin, http_calls: list[HttpOptions]
) -> None:
    cli.main(["serve", "--transport", "http", "--no-auth"])
    assert joplin.requests == []


def test_reindex_with_a_wrong_filter_exits_2_and_says_why_once(
    joplin: FakeJoplin, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    index = FakeVectorIndex()
    monkeypatch.setattr(backends, "build_embedder", lambda settings: FakeEmbedder())
    monkeypatch.setattr(backends, "build_vector_index", lambda settings, model_name: index)
    monkeypatch.setenv("SBJ_NOTEBOOKS", "Wrok")
    with pytest.raises(SystemExit) as exc:
        cli.main(["reindex", "--full"])
    assert exc.value.code == 2
    assert capsys.readouterr().err.count("no notebook is titled 'Wrok'") == 1
    assert index.note_versions() == {}
