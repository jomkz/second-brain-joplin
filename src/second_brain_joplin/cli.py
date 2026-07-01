"""Command-line entry point for the Joplin MCP server."""

import argparse

from dotenv import load_dotenv

from . import __version__
from .server import mcp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="second-brain-joplin",
        description="MCP server for Joplin knowledge bases.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("serve", help="Start the MCP server (stdio transport).")
    return parser


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "serve":
        mcp.run()
    else:
        parser.print_help()


if __name__ == "__main__":  # pragma: no cover
    main()
