"""Command-line entry point for the Joplin MCP server."""

import argparse
import asyncio
import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

from . import __version__
from .audit import configure_logging
from .auth import AuthSettings, build_auth
from .config import Settings
from .context import AppContext
from .errors import JoplinError, NotebookFilterError, SemanticUnavailableError
from .joplin_client import JoplinClient, JsonDict
from .remote import ServeConfigError, http_options, run_http, validate
from .scope import NotebookScope, check_at_startup, scope_of
from .semantic.types import SyncStats
from .server import create_server, mcp

TRANSPORTS = ("stdio", "http")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="second-brain-joplin",
        description="MCP server for Joplin knowledge bases.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")
    serve = subparsers.add_parser(
        "serve",
        help="Start the MCP server (stdio by default, or streamable HTTP).",
        description=(
            "Start the MCP server. stdio is for a client on this machine (Claude Code); "
            "http is for a remote client such as a Claude custom connector "
            "(docs/remote-access.md). Every option falls back to the SBJ_* variable named."
        ),
    )
    serve.add_argument(
        "--transport", choices=TRANSPORTS, help="stdio (default) or http  [SBJ_TRANSPORT]"
    )
    serve.add_argument("--host", help="HTTP: address to bind (default 127.0.0.1)  [SBJ_HOST]")
    serve.add_argument(
        "--port", type=int, help="HTTP: port to listen on (default 8775)  [SBJ_PORT]"
    )
    serve.add_argument("--path", help="HTTP: MCP endpoint path (default /mcp)  [SBJ_HTTP_PATH]")
    serve.add_argument(
        "--public-url",
        help="HTTP: the server's public origin, e.g. https://joplin.example.com  [SBJ_PUBLIC_URL]",
    )
    serve.add_argument(
        "--no-auth",
        action="store_true",
        help="HTTP: run without sign-in, on a loopback address only (local testing)",
    )
    serve.add_argument(
        "--env-file",
        type=Path,
        help="load settings and secrets from this file first (variables already set win)",
    )
    reindex = subparsers.add_parser(
        "reindex",
        help="Build or update the semantic index, with no time limit.",
        description=(
            "Sync the semantic index against Joplin from the command line. Use it for a "
            "first build or a full rebuild, which can take longer than a remote tool "
            "call may run. Needs the [semantic] extra and Joplin Desktop running."
        ),
    )
    reindex.add_argument("--full", action="store_true", help="re-embed every note from scratch")
    reindex.add_argument(
        "--env-file", type=Path, help="load settings from this file first (set variables win)"
    )
    notebooks = subparsers.add_parser(
        "notebooks",
        help="List the notebooks with their ids and what the notebook filter shows.",
        description=(
            "Print every notebook with its id and note count, marked visible or hidden "
            "under SBJ_NOTEBOOKS / SBJ_EXCLUDE_NOTEBOOKS. Use it to find the ids for "
            "those variables, and to check a filter before a client sees through it. "
            "Needs Joplin Desktop running."
        ),
    )
    notebooks.add_argument(
        "--env-file", type=Path, help="load settings from this file first (set variables win)"
    )
    return parser


async def run_reindex(full: bool) -> SyncStats:
    """Sync the index once, outside any server, and return what changed."""
    settings = Settings.from_env()
    client = JoplinClient(settings)
    try:
        return await AppContext(client=client, settings=settings).semantic().sync(full=full)
    finally:
        await client.aclose()


def reindex(args: argparse.Namespace) -> None:
    stats = asyncio.run(run_reindex(args.full))
    print(
        f"added={stats.added} updated={stats.updated} deleted={stats.deleted} "
        f"total={stats.total} model={stats.model_name}"
    )


def notebook_lines(
    folders: list[JsonDict], notes_index: list[JsonDict], scope: NotebookScope | None
) -> list[str]:
    """One line per notebook, as an indented tree: mark, id, title and note count.

    Every notebook is listed, hidden ones too: this is the operator's own view.
    ``scope`` is None when the filter doesn't resolve, and the mark is then ``?``.
    """
    counts: dict[str, int] = {}
    for note in notes_index:
        parent = note.get("parent_id", "")
        counts[parent] = counts.get(parent, 0) + 1
    ids = {folder["id"] for folder in folders}
    children_of: dict[str, list[JsonDict]] = {}
    for folder in sorted(folders, key=lambda f: str(f.get("title", "")).casefold()):
        parent = folder.get("parent_id", "")
        children_of.setdefault(parent if parent in ids else "", []).append(folder)

    lines: list[str] = []

    def walk(parent: str, depth: int) -> None:
        for folder in children_of.get(parent, []):
            if scope is None:
                mark = "?"
            else:
                mark = "visible" if scope.allows(folder["id"]) else "hidden"
            title = folder.get("title", "")
            count = counts.get(folder["id"], 0)
            lines.append(f"{mark:<7}  {folder['id']}  {'  ' * depth}{title} ({count})")
            walk(folder["id"], depth + 1)

    walk("", 0)
    return lines


async def fetch_notebooks(settings: Settings) -> tuple[list[JsonDict], list[JsonDict]]:
    """Joplin's notebooks and its note index (ids and notebooks only, no content)."""
    client = JoplinClient(settings)
    try:
        return await client.get_folders(), await client.get_notes_index()
    finally:
        await client.aclose()


def notebooks(_args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    folders, notes_index = asyncio.run(fetch_notebooks(settings))
    try:
        scope = scope_of(settings, folders)
    except NotebookFilterError:
        # Show the tree anyway: its ids are what fixes the filter.
        print("\n".join(notebook_lines(folders, notes_index, None)))
        raise
    if scope.visible is None:
        print(f"No notebook filter is set: all {len(folders)} notebooks are visible.")
    else:
        print(f"Notebook filter: {len(scope.visible)} of {len(folders)} notebooks visible.")
    print("\n".join(notebook_lines(folders, notes_index, scope)))


def load_env_file(path: Path) -> None:
    """Load ``KEY=value`` lines from ``path`` into the environment, keeping set ones.

    For service managers like launchd that can't load an env file themselves. A file
    that is missing or unreadable is an error, not a silent no-op.
    """
    if not path.is_file():
        raise ServeConfigError(f"--env-file {path} does not exist or is not a file")
    for name, value in dotenv_values(path).items():
        if value is not None:
            os.environ.setdefault(name, value)


def serve(args: argparse.Namespace) -> None:
    transport = args.transport or os.environ.get("SBJ_TRANSPORT") or "stdio"
    if transport not in TRANSPORTS:
        raise ServeConfigError(f"SBJ_TRANSPORT must be one of {', '.join(TRANSPORTS)}")
    if transport == "stdio":
        http_only = [
            flag
            for flag, value in (
                ("--host", args.host),
                ("--port", args.port),
                ("--path", args.path),
                ("--public-url", args.public_url),
                ("--no-auth", args.no_auth or None),
            )
            if value is not None
        ]
        if http_only:
            raise ServeConfigError(f"{', '.join(http_only)} only apply to --transport http")
        asyncio.run(check_at_startup(Settings.from_env()))
        mcp.run()
        return
    options = http_options(
        host=args.host,
        port=args.port,
        path=args.path,
        public_url=args.public_url,
        no_auth=args.no_auth,
    )
    auth_settings = AuthSettings.from_env()
    validate(options, auth_configured=auth_settings is not None)
    configure_logging()
    asyncio.run(check_at_startup(Settings.from_env()))
    auth = None
    if auth_settings is not None:
        assert options.public_url is not None  # validate() guarantees it with sign-in
        auth = build_auth(auth_settings, options.public_url)
    server = create_server(
        auth=auth,
        allowed_ids=auth_settings.allowed_ids if auth_settings else None,
        rate_limit_per_minute=options.rate_limit_per_minute,
        remote=True,
        sync_interval_minutes=options.sync_interval_minutes,
    )
    run_http(server, options)


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return
    try:
        if getattr(args, "env_file", None) is not None:
            load_env_file(args.env_file)
        load_dotenv()
        if args.command == "serve":
            serve(args)
        elif args.command == "reindex":
            reindex(args)
        elif args.command == "notebooks":
            notebooks(args)
    except ServeConfigError as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    except NotebookFilterError as exc:
        # A configuration error like the ones above. The detail names the entry at
        # fault; this is the operator's terminal, so it may.
        parser.exit(2, f"{parser.prog}: error: {exc.detail}\n")
    except (SemanticUnavailableError, JoplinError) as exc:
        parser.exit(1, f"{parser.prog}: error: {exc}\n")


if __name__ == "__main__":  # pragma: no cover
    main()
