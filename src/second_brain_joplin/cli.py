"""Command-line entry point for the Joplin MCP server."""

import argparse
import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

from . import __version__
from .auth import AuthSettings, build_auth
from .remote import ServeConfigError, http_options, run_http, validate
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
    return parser


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
    if auth_settings is None:
        run_http(create_server(), options)
        return
    assert options.public_url is not None  # validate() guarantees it with sign-in
    run_http(
        create_server(
            auth=build_auth(auth_settings, options.public_url),
            allowed_ids=auth_settings.allowed_ids,
        ),
        options,
    )


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
    except ServeConfigError as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")


if __name__ == "__main__":  # pragma: no cover
    main()
