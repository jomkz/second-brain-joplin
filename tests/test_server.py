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
    "joplin_semantic_search",
    "joplin_reindex",
}

# tool name -> required input parameters (ctx is injected, not user-facing)
REQUIRED_PARAMS = {
    "joplin_overview": set(),
    "joplin_search": {"query"},
    "joplin_read": {"note_id"},
    "joplin_recent": set(),
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

    schema = tools[tool_name].input_schema
    properties = set(schema.get("properties", {}))
    assert REQUIRED_PARAMS[tool_name] <= properties
    assert "ctx" not in properties
    if REQUIRED_PARAMS[tool_name]:
        assert REQUIRED_PARAMS[tool_name] <= set(schema.get("required", []))


async def test_joplin_recent_defaults_to_seven_days() -> None:
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
    days = tools["joplin_recent"].input_schema["properties"]["days"]
    assert days["default"] == 7


async def test_no_write_tool_is_registered() -> None:
    """joplin_create returns with the human-gated flow (v0.5, #10), not before."""
    async with Client(mcp) as client:
        names = {tool.name for tool in await client.list_tools()}
    assert "joplin_create" not in names


# Tools that change something: tool name -> why. Every other tool must be read-only.
LOCAL_WRITERS = {"joplin_reindex": "updates the local search index only"}


async def test_every_tool_declares_its_side_effects() -> None:
    """Walks the live tool list, so a new tool can't ship without annotations."""
    async with Client(mcp) as client:
        tools = await client.list_tools()
    for tool in tools:
        hints = tool.annotations
        assert hints is not None, f"{tool.name} has no annotations"
        assert hints.open_world_hint is False, tool.name
        if tool.name in LOCAL_WRITERS:
            assert hints.read_only_hint is False, tool.name
            assert hints.destructive_hint is False, tool.name
            assert hints.idempotent_hint is True, tool.name
        else:
            assert hints.read_only_hint is True, tool.name


@pytest.mark.parametrize(
    ("tool_name", "param", "low", "high"),
    [
        ("joplin_search", "limit", 1, 50),
        ("joplin_semantic_search", "limit", 1, 50),
        ("joplin_recent", "limit", 1, 100),
        ("joplin_recent", "days", 1, 3650),
        ("joplin_read", "max_chars", 1, 100_000),
    ],
)
async def test_bounds_are_in_the_schema(tool_name: str, param: str, low: int, high: int) -> None:
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
    schema = tools[tool_name].input_schema["properties"][param]
    assert (schema["minimum"], schema["maximum"]) == (low, high)


async def test_lifespan_yields_app_context_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    closed: dict[str, bool] = {}

    async def fake_aclose(self: JoplinClient) -> None:
        closed["ran"] = True

    monkeypatch.setattr(JoplinClient, "aclose", fake_aclose)

    async with lifespan(mcp) as app_ctx:
        assert isinstance(app_ctx, AppContext)
        assert isinstance(app_ctx.client, JoplinClient)
    assert closed.get("ran") is True
