#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["fastmcp>=4.1,<5"]
# ///
"""Start second-brain-joplin the way a user does, with uvx, and talk MCP to it.

    uv run scripts/smoke.py                                    # the latest release on PyPI
    uv run scripts/smoke.py --from "second-brain-joplin==1.0.0"
    uv run scripts/smoke.py --from dist/second_brain_joplin-1.0.0-py3-none-any.whl
    uv run scripts/smoke.py --python 3.13                      # on a chosen Python
    uv run scripts/smoke.py --live                             # also read a running Joplin
    uv run scripts/smoke.py --semantic --from "second-brain-joplin[semantic]"

Without --live it needs no Joplin: it points the server at a closed port and
checks that the server installs, starts on both transports, lists the right
tools and turns "Joplin isn't there" into a clear error. CI runs it that way on
Linux, macOS and Windows against the wheel it just built.

--live reads from a real Joplin, taking JOPLIN_API_TOKEN (and JOPLIN_BASE_URL)
from the environment or from --env-file. It only reads, and prints counts and
lengths, never a title or a line of a note.

--semantic loads the embedding model and the vector store, in a temporary index
directory. It downloads the model on first use, so CI leaves it out.
"""

import argparse
import asyncio
import contextlib
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

READ_TOOLS = {
    "joplin_overview",
    "joplin_search",
    "joplin_read",
    "joplin_recent",
    "joplin_semantic_search",
    "joplin_reindex",
}
WRITE_TOOL = "joplin_create_note"
# A first run installs the package and its dependencies before the server speaks.
START_TIMEOUT = 300
# What the stdio servers write to stderr; shown only when a check fails.
SERVER_LOG = Path(tempfile.gettempdir()) / f"sbj-smoke-{os.getpid()}.log"
failures: list[str] = []


def check(ok: bool, what: str, detail: str = "") -> bool:
    print(f"{'ok  ' if ok else 'FAIL'}  {what}{f': {detail}' if detail else ''}", flush=True)
    if not ok:
        failures.append(what)
    return ok


def free_port() -> int:
    """A port nothing listens on: taken, then given back."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        name, sep, value = line.strip().partition("=")
        if sep and name and not name.startswith("#"):
            values[name.strip()] = value.strip().strip("'\"")
    return values


def base_env() -> dict[str, str]:
    """This process's environment without any server setting, so each check sets its own."""
    return {k: v for k, v in os.environ.items() if not k.startswith(("SBJ_", "JOPLIN_"))}


def text_of(result: Any) -> str:
    return " ".join(getattr(block, "text", "") for block in result.content)


class Server:
    """How to start the server under test: `uvx [--python X] --from SPEC second-brain-joplin`."""

    def __init__(self, spec: str, python: str | None) -> None:
        self.prefix = ["uvx", *(["--python", python] if python else []), "--from", spec]

    def command(self, *args: str) -> list[str]:
        return [*self.prefix, "second-brain-joplin", *args]

    def stdio(self, env: dict[str, str]) -> Client[Any]:
        command = self.command("serve")
        transport = StdioTransport(
            command[0], command[1:], env=env, keep_alive=False, log_file=SERVER_LOG
        )
        return Client(transport, init_timeout=START_TIMEOUT)


async def tool_names(client: Client[Any]) -> set[str]:
    return {tool.name for tool in await client.list_tools()}


async def check_stdio(server: Server, joplin_down: dict[str, str]) -> None:
    async with server.stdio(joplin_down) as client:
        info = client.server_info
        check(
            info is not None and info.name == "second-brain-joplin",
            "stdio: the server says who it is",
            f"{info.name if info else None}, MCP {client.protocol_version}",
        )
        names = await tool_names(client)
        check(names == READ_TOOLS, "stdio: exactly the six read-only tools", f"{len(names)} listed")
        result = await client.call_tool("joplin_overview", raise_on_error=False)
        message = text_of(result)
        check(
            result.is_error and "Joplin is unreachable" in message,
            "stdio: a call with Joplin down says so",
            message[:90],
        )
        result = await client.call_tool("joplin_read", {"note_id": "nope"}, raise_on_error=False)
        check(result.is_error, "stdio: a note id that isn't a Joplin id is refused")

    async with server.stdio({**joplin_down, "SBJ_WRITE_NOTEBOOKS": "Inbox"}) as client:
        names = await tool_names(client)
        check(
            names == READ_TOOLS | {WRITE_TOOL},
            "stdio: SBJ_WRITE_NOTEBOOKS adds joplin_create_note and nothing else",
        )


def stop(process: subprocess.Popen[bytes]) -> None:
    """Stop uvx and the server it started (on Windows the child outlives a plain kill)."""
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False
        )
    else:
        os.killpg(process.pid, signal.SIGTERM)
    process.wait(timeout=30)


def get_json(url: str) -> tuple[int, Any]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:  # /healthz answers 503 with a body
        return error.code, json.load(error)


async def check_http(server: Server, joplin_down: dict[str, str]) -> None:
    port = free_port()
    group: dict[str, Any] = {} if sys.platform == "win32" else {"start_new_session": True}
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen(
            server.command("serve", "--transport", "http", "--no-auth", "--port", str(port)),
            env=joplin_down,
            stdout=log,
            stderr=subprocess.STDOUT,
            **group,
        )
        try:
            health: tuple[int, Any] | None = None
            deadline = time.monotonic() + START_TIMEOUT
            while health is None and process.poll() is None and time.monotonic() < deadline:
                try:
                    health = get_json(f"http://127.0.0.1:{port}/healthz")
                except OSError:
                    await asyncio.sleep(0.5)
            if not check(health is not None, "http: the server starts with --no-auth on loopback"):
                log.seek(0)
                print(log.read().decode(errors="replace")[-2000:])
                return
            check(
                health == (503, {"server": True, "joplin": False}),
                "http: /healthz reports Joplin down with 503",
                str(health),
            )
            async with Client(f"http://127.0.0.1:{port}/mcp", init_timeout=30) as client:
                check(await tool_names(client) == READ_TOOLS, "http: MCP lists the same six tools")
        finally:
            stop(process)


async def check_semantic(server: Server, joplin_down: dict[str, str]) -> None:
    """The model and the vector store load: the search gets as far as asking Joplin."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as index_dir:
        async with server.stdio({**joplin_down, "SBJ_INDEX_DIR": index_dir}) as client:
            result = await client.call_tool(
                "joplin_semantic_search",
                {"query": "anything"},
                raise_on_error=False,
                timeout=START_TIMEOUT,
            )
            message = text_of(result)
            check(
                result.is_error and "Joplin is unreachable" in message,
                "semantic: the embedding model and the vector store load",
                message[:120],
            )


async def check_live(server: Server, env: dict[str, str], semantic: bool) -> None:
    """Read a real Joplin. Counts and lengths only: nothing a note says is printed."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as index_dir:
        async with server.stdio({**env, "SBJ_INDEX_DIR": index_dir}) as client:
            notebooks = (await client.call_tool("joplin_overview")).structured_content["result"]
            check(len(notebooks) > 0, "live: joplin_overview lists notebooks", str(len(notebooks)))
            recent = (
                await client.call_tool("joplin_recent", {"days": 3650, "limit": 5})
            ).structured_content["result"]
            check(len(recent) > 0, "live: joplin_recent lists notes", str(len(recent)))
            if recent:
                note = (
                    await client.call_tool(
                        "joplin_read", {"note_id": recent[0]["id"], "max_chars": 200}
                    )
                ).structured_content
                check(
                    note["id"] == recent[0]["id"] and len(note["body"]) <= 200,
                    "live: joplin_read returns a page of the newest note",
                    f"{len(note['body'])} of {note['total_chars']} characters",
                )
            hits = (
                await client.call_tool("joplin_search", {"query": "a*", "limit": 3})
            ).structured_content["result"]
            check(isinstance(hits, list), "live: joplin_search answers", f"{len(hits)} hits")
            if semantic:
                stats = (await client.call_tool("joplin_reindex", timeout=3600)).structured_content
                check(stats["total"] > 0, "live: joplin_reindex builds an index", json.dumps(stats))
                found = (
                    await client.call_tool("joplin_semantic_search", {"query": "notes", "limit": 3})
                ).structured_content["result"]
                check(len(found) > 0, "live: joplin_semantic_search finds notes", str(len(found)))
            else:
                result = await client.call_tool(
                    "joplin_semantic_search", {"query": "notes"}, raise_on_error=False
                )
                check(
                    result.is_error and "[semantic]" in text_of(result),
                    "live: without the extra, semantic search says how to install it",
                )


async def run(args: argparse.Namespace) -> None:
    server = Server(args.spec, args.python)
    version = subprocess.run(
        server.command("--version"), capture_output=True, text=True, check=False, timeout=600
    )
    shown = version.stdout.strip()
    if not check(version.returncode == 0, "uvx installs and runs the package", shown):
        print(version.stderr[-2000:])
        return
    if args.expect:
        check(shown == f"second-brain-joplin {args.expect}", f"the version is {args.expect}")
    python = subprocess.run(
        [*server.prefix, "python", "-c", "import platform; print(platform.python_version())"],
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    print(f"      the server runs on Python {python.stdout.strip() or '?'}", flush=True)

    joplin_down = {
        **base_env(),
        "JOPLIN_BASE_URL": f"http://127.0.0.1:{free_port()}",
        "JOPLIN_API_TOKEN": "smoke-test",
    }
    await check_stdio(server, joplin_down)
    await check_http(server, joplin_down)
    if args.semantic:
        await check_semantic(server, joplin_down)
    if args.live:
        settings = read_env_file(args.env_file) if args.env_file else dict(os.environ)
        live = {k: v for k, v in settings.items() if k in ("JOPLIN_API_TOKEN", "JOPLIN_BASE_URL")}
        if check("JOPLIN_API_TOKEN" in live, "live: a Joplin token is set"):
            await check_live(server, {**base_env(), **live}, args.semantic)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--from",
        dest="spec",
        default="second-brain-joplin",
        help="what uvx installs: a requirement or a wheel (default: the latest on PyPI)",
    )
    parser.add_argument("--python", help="the Python uvx runs it on, e.g. 3.13")
    parser.add_argument("--expect", metavar="VERSION", help="fail unless this version starts")
    parser.add_argument("--semantic", action="store_true", help="also load the semantic stack")
    parser.add_argument("--live", action="store_true", help="also read from a running Joplin")
    parser.add_argument("--env-file", type=Path, help="with --live: read the Joplin token here")
    args = parser.parse_args(argv)
    print(f"{sys.platform}, Python {sys.version.split()[0]}, testing {args.spec}", flush=True)
    try:
        asyncio.run(run(args))
        if failures and SERVER_LOG.exists():
            print(SERVER_LOG.read_text(encoding="utf-8", errors="replace")[-4000:])
    finally:
        with contextlib.suppress(OSError):  # Windows: a server may still hold it
            SERVER_LOG.unlink(missing_ok=True)
    print(f"{len(failures)} failed" if failures else "all passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
