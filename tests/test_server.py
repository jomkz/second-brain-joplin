"""Tests for the MCP server: tool registration, schemas, and lifespan wiring."""

import pytest
from fastmcp import Client

from second_brain_joplin.context import AppContext
from second_brain_joplin.joplin_client import JoplinClient
from second_brain_joplin.server import lifespan, mcp

EXPECTED_TOOLS = {
    "joplin_overview",
    "joplin_search",
    "joplin_read",
    "joplin_recent",
    "joplin_create",
    "joplin_semantic_search",
    "joplin_reindex",
}

# tool name -> required input parameters (ctx is injected, not user-facing)
REQUIRED_PARAMS = {
    "joplin_overview": set(),
    "joplin_search": {"query"},
    "joplin_read": {"note_id"},
    "joplin_recent": set(),
    "joplin_create": {"title", "body", "notebook_id"},
    "joplin_semantic_search": {"query"},
    "joplin_reindex": set(),
}


async def test_all_tools_registered() -> None:
    async with Client(mcp) as client:
        names = {tool.name for tool in await client.list_tools()}
    assert names == EXPECTED_TOOLS


@pytest.mark.parametrize("tool_name", sorted(EXPECTED_TOOLS))
async def test_tool_input_schema_exposes_required_params(tool_name: str) -> None:
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}

    schema = tools[tool_name].inputSchema
    properties = set(schema.get("properties", {}))
    assert REQUIRED_PARAMS[tool_name] <= properties
    assert "ctx" not in properties
    if REQUIRED_PARAMS[tool_name]:
        assert REQUIRED_PARAMS[tool_name] <= set(schema.get("required", []))


async def test_joplin_recent_defaults_to_seven_days() -> None:
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
    days = tools["joplin_recent"].inputSchema["properties"]["days"]
    assert days["default"] == 7


async def test_joplin_create_is_still_stubbed() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool(
            "joplin_create", {"title": "t", "body": "b", "notebook_id": "n"}
        )
    assert result.data["status"] == "not implemented"
    assert result.data["tool"] == "joplin_create"


async def test_lifespan_yields_app_context_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    closed: dict[str, bool] = {}

    async def fake_aclose(self: JoplinClient) -> None:
        closed["ran"] = True

    monkeypatch.setattr(JoplinClient, "aclose", fake_aclose)

    async with lifespan(mcp) as app_ctx:
        assert isinstance(app_ctx, AppContext)
        assert isinstance(app_ctx.client, JoplinClient)
    assert closed.get("ran") is True
