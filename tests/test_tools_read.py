"""Tests for the read MCP tools, driven through a FastMCP client."""

import time

import httpx
import pytest
import respx
from fastmcp import Client
from fastmcp.exceptions import ToolError

from second_brain_joplin.server import mcp

BASE_URL = "http://localhost:41184"


def _ms(seconds_ago: float) -> int:
    return int((time.time() - seconds_ago) * 1000)


def _attr(obj, name):
    """Read a field whether FastMCP returned a model instance or a dict."""
    return obj[name] if isinstance(obj, dict) else getattr(obj, name)


@respx.mock
async def test_overview_builds_tree_with_counts():
    respx.get(f"{BASE_URL}/folders").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {"id": "root", "title": "Inbox", "parent_id": ""},
                    {"id": "child", "title": "Sub", "parent_id": "root"},
                ],
                "has_more": False,
            },
        )
    )
    respx.get(f"{BASE_URL}/notes").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {"id": "n1", "parent_id": "root"},
                    {"id": "n2", "parent_id": "child"},
                    {"id": "n3", "parent_id": "root"},
                ],
                "has_more": False,
            },
        )
    )
    async with Client(mcp) as client:
        result = await client.call_tool("joplin_overview", {})

    tree = result.data
    assert len(tree) == 1
    assert _attr(tree[0], "name") == "Inbox"
    assert _attr(tree[0], "note_count") == 2
    child = _attr(tree[0], "children")[0]
    assert _attr(child, "name") == "Sub"
    assert _attr(child, "note_count") == 1


@respx.mock
async def test_search_returns_excerpts():
    long_body = "word " * 100  # > 200 chars once joined
    respx.get(f"{BASE_URL}/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [{"id": "1", "title": "A", "body": long_body}],
                "has_more": False,
            },
        )
    )
    async with Client(mcp) as client:
        result = await client.call_tool("joplin_search", {"query": "word"})

    hit = result.data[0]
    assert _attr(hit, "id") == "1"
    excerpt = _attr(hit, "excerpt")
    assert excerpt.endswith("…")
    assert len(excerpt) <= 201


@respx.mock
async def test_search_empty_returns_empty_list():
    respx.get(f"{BASE_URL}/search").mock(
        return_value=httpx.Response(200, json={"items": [], "has_more": False})
    )
    async with Client(mcp) as client:
        result = await client.call_tool("joplin_search", {"query": "nomatch"})
    assert result.data == []


@respx.mock
async def test_read_converts_timestamps():
    respx.get(f"{BASE_URL}/notes/abc").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "abc",
                "title": "T",
                "body": "hello",
                "parent_id": "root",
                "created_time": 0,
                "updated_time": 0,
            },
        )
    )
    async with Client(mcp) as client:
        result = await client.call_tool("joplin_read", {"note_id": "abc"})

    note = result.data
    assert _attr(note, "title") == "T"
    assert _attr(note, "body") == "hello"
    assert _attr(note, "created_time").startswith("1970-01-01T00:00:00")


@respx.mock
async def test_read_missing_note_raises_tool_error():
    respx.get(f"{BASE_URL}/notes/missing").mock(return_value=httpx.Response(404))
    async with Client(mcp) as client:
        with pytest.raises(ToolError):
            await client.call_tool("joplin_read", {"note_id": "missing"})


@respx.mock
async def test_recent_filters_by_days():
    respx.get(f"{BASE_URL}/notes").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {"id": "new", "title": "New", "updated_time": _ms(60)},
                    {"id": "old", "title": "Old", "updated_time": _ms(60 * 60 * 24 * 30)},
                ],
                "has_more": False,
            },
        )
    )
    async with Client(mcp) as client:
        result = await client.call_tool("joplin_recent", {"days": 7})

    ids = [_attr(note, "id") for note in result.data]
    assert ids == ["new"]


@respx.mock
async def test_tool_surfaces_connection_error():
    respx.get(f"{BASE_URL}/folders").mock(side_effect=httpx.ConnectError("boom"))
    async with Client(mcp) as client:
        with pytest.raises(ToolError):
            await client.call_tool("joplin_overview", {})
