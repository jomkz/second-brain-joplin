"""Tests for the MCP server: tool registration, stub payloads, and wiring."""

import pytest
from fastmcp import Client

from second_brain_joplin import server
from second_brain_joplin.server import mcp

EXPECTED_TOOLS = {
    "joplin_overview",
    "joplin_search",
    "joplin_read",
    "joplin_recent",
    "joplin_create",
}

# tool name -> required input parameters (per issue #3 / README)
REQUIRED_PARAMS = {
    "joplin_overview": set(),
    "joplin_search": {"query"},
    "joplin_read": {"note_id"},
    "joplin_recent": set(),
    "joplin_create": {"title", "body", "notebook_id"},
}


async def test_all_five_tools_registered():
    async with Client(mcp) as client:
        names = {tool.name for tool in await client.list_tools()}
    assert names == EXPECTED_TOOLS


@pytest.mark.parametrize("tool_name", sorted(EXPECTED_TOOLS))
async def test_tool_returns_not_implemented_stub(tool_name):
    # Minimal valid args per tool.
    args = {
        "joplin_search": {"query": "x"},
        "joplin_read": {"note_id": "abc"},
        "joplin_create": {"title": "t", "body": "b", "notebook_id": "n"},
    }.get(tool_name, {})

    async with Client(mcp) as client:
        result = await client.call_tool(tool_name, args)

    assert result.data["status"] == "not implemented"
    assert result.data["tool"] == tool_name


@pytest.mark.parametrize("tool_name", sorted(EXPECTED_TOOLS))
async def test_tool_input_schema_exposes_required_params(tool_name):
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}

    schema = tools[tool_name].inputSchema
    properties = set(schema.get("properties", {}))
    assert REQUIRED_PARAMS[tool_name] <= properties
    if REQUIRED_PARAMS[tool_name]:
        assert set(schema.get("required", [])) == REQUIRED_PARAMS[tool_name]


async def test_joplin_recent_defaults_to_seven_days():
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
    days = tools["joplin_recent"].inputSchema["properties"]["days"]
    assert days["default"] == 7


def test_get_client_reads_env(monkeypatch):
    monkeypatch.setenv("JOPLIN_API_TOKEN", "secret")
    monkeypatch.setenv("JOPLIN_BASE_URL", "http://example:9999")
    client = server._get_client()
    assert client.base_url == "http://example:9999"
    assert client._params["token"] == "secret"


def test_get_client_defaults_when_env_unset(monkeypatch):
    monkeypatch.delenv("JOPLIN_API_TOKEN", raising=False)
    monkeypatch.delenv("JOPLIN_BASE_URL", raising=False)
    client = server._get_client()
    assert client.base_url == "http://localhost:41184"
    assert client._params["token"] == ""


def test_get_client_is_singleton():
    assert server._get_client() is server._get_client()


def test_main_serve_invokes_mcp_run(monkeypatch):
    called = {}
    monkeypatch.setattr(server.mcp, "run", lambda: called.setdefault("ran", True))
    server.main(["serve"])
    assert called.get("ran") is True


def test_main_without_command_prints_help(monkeypatch, capsys):
    monkeypatch.setattr(server.mcp, "run", lambda: pytest.fail("mcp.run should not be called"))
    server.main([])
    out = capsys.readouterr().out
    assert "serve" in out
