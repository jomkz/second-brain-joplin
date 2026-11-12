"""Tests for the read MCP tools, driven through a FastMCP client."""

import time
from typing import Any

import httpx
import pytest
import respx
from fastmcp import Client
from fastmcp.exceptions import ToolError

from second_brain_joplin.server import mcp

BASE_URL = "http://localhost:41184"

# Note ids in Joplin's shape (32 hexadecimal characters); the tools take no other.
ABC = "abc".ljust(32, "0")
MISSING = "0" * 32
LONG = "1" * 32


def _ms(seconds_ago: float) -> int:
    return int((time.time() - seconds_ago) * 1000)


def _attr(obj: object, name: str) -> Any:
    """Read a field whether FastMCP returned a model instance or a dict."""
    return obj[name] if isinstance(obj, dict) else getattr(obj, name)


@respx.mock
async def test_overview_builds_tree_with_counts() -> None:
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
async def test_search_returns_excerpts() -> None:
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
async def test_search_empty_returns_empty_list() -> None:
    respx.get(f"{BASE_URL}/search").mock(
        return_value=httpx.Response(200, json={"items": [], "has_more": False})
    )
    async with Client(mcp) as client:
        result = await client.call_tool("joplin_search", {"query": "nomatch"})
    assert result.data == []


@respx.mock
async def test_read_converts_timestamps() -> None:
    respx.get(f"{BASE_URL}/notes/{ABC}").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": ABC,
                "title": "T",
                "body": "hello",
                "parent_id": "root",
                "created_time": 0,
                "updated_time": 0,
            },
        )
    )
    async with Client(mcp) as client:
        result = await client.call_tool("joplin_read", {"note_id": ABC})

    note = result.data
    assert _attr(note, "title") == "T"
    assert _attr(note, "body") == "hello"
    assert _attr(note, "created_time").startswith("1970-01-01T00:00:00")


@respx.mock
async def test_read_missing_note_raises_tool_error() -> None:
    respx.get(f"{BASE_URL}/notes/{MISSING}").mock(return_value=httpx.Response(404))
    async with Client(mcp) as client:
        with pytest.raises(ToolError, match="was not found"):
            await client.call_tool("joplin_read", {"note_id": MISSING})


@respx.mock
async def test_recent_filters_by_days() -> None:
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
async def test_tool_surfaces_connection_error() -> None:
    respx.get(f"{BASE_URL}/folders").mock(side_effect=httpx.ConnectError("boom"))
    async with Client(mcp) as client:
        with pytest.raises(ToolError):
            await client.call_tool("joplin_overview", {})


def _mock_note(body: str) -> None:
    respx.get(f"{BASE_URL}/notes/{LONG}").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": LONG,
                "title": "Long",
                "body": body,
                "parent_id": "root",
                "created_time": 0,
                "updated_time": 0,
            },
        )
    )


async def _read(**args: Any) -> Any:
    async with Client(mcp) as client:
        result = await client.call_tool("joplin_read", {"note_id": LONG, **args})
    return result.data


@respx.mock
async def test_read_short_note_is_one_page() -> None:
    _mock_note("hello")
    note = await _read()
    assert (_attr(note, "body"), _attr(note, "total_chars")) == ("hello", 5)
    assert _attr(note, "offset") == 0
    assert _attr(note, "next_offset") is None


@respx.mock
async def test_read_pages_through_a_long_note() -> None:
    body = "".join(str(i % 10) for i in range(25))
    _mock_note(body)
    pages, offset = [], 0
    while offset is not None:
        note = await _read(offset=offset, max_chars=10)
        pages.append(_attr(note, "body"))
        assert _attr(note, "total_chars") == 25
        offset = _attr(note, "next_offset")
    assert pages == [body[0:10], body[10:20], body[20:25]]
    assert "".join(pages) == body


@respx.mock
async def test_read_page_ending_exactly_at_the_end_has_no_next() -> None:
    _mock_note("x" * 20)
    note = await _read(offset=10, max_chars=10)
    assert _attr(note, "body") == "x" * 10
    assert _attr(note, "next_offset") is None


@respx.mock
async def test_read_past_the_end_is_empty_not_an_error() -> None:
    _mock_note("short")
    note = await _read(offset=100)
    assert (_attr(note, "body"), _attr(note, "total_chars")) == ("", 5)
    assert _attr(note, "next_offset") is None


@respx.mock
async def test_read_counts_characters_not_bytes() -> None:
    body = "😀é漢" * 4  # 12 characters, 36 bytes in UTF-8
    _mock_note(body)
    first = await _read(max_chars=5)
    second = await _read(offset=5, max_chars=100)
    assert _attr(first, "total_chars") == 12
    assert _attr(first, "body") + _attr(second, "body") == body


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("joplin_search", {"query": "q", "limit": 0}),
        ("joplin_search", {"query": "q", "limit": -1}),
        ("joplin_search", {"query": "q", "limit": 51}),
        ("joplin_search", {"query": "q", "limit": 10**9}),
        ("joplin_recent", {"limit": 0}),
        ("joplin_recent", {"limit": 101}),
        ("joplin_recent", {"days": 0}),
        ("joplin_recent", {"days": 3651}),
        ("joplin_read", {"note_id": LONG, "offset": -1}),
        ("joplin_read", {"note_id": LONG, "max_chars": 0}),
        ("joplin_read", {"note_id": LONG, "max_chars": 100_001}),
        # Not an id: nothing that could reach another Joplin endpoint gets through.
        ("joplin_read", {"note_id": "abc"}),
        ("joplin_read", {"note_id": ""}),
        ("joplin_read", {"note_id": f"../folders/{LONG}"}),
        ("joplin_read", {"note_id": f"{LONG}/resources"}),
        ("joplin_read", {"note_id": f"{LONG}?fields=body"}),
        ("joplin_read", {"note_id": LONG + "\n"}),
        ("joplin_semantic_search", {"query": "q", "limit": 0}),
        ("joplin_semantic_search", {"query": "q", "limit": 51}),
    ],
)
async def test_out_of_range_arguments_are_refused_before_joplin_is_called(
    tool: str, args: dict[str, Any]
) -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.route(host="localhost")
        async with Client(mcp) as client:
            with pytest.raises(ToolError):
                await client.call_tool(tool, args)
    assert not route.called


@respx.mock
async def test_limits_at_the_ceiling_are_accepted() -> None:
    respx.get(f"{BASE_URL}/search").mock(
        return_value=httpx.Response(200, json={"items": [], "has_more": False})
    )
    async with Client(mcp) as client:
        result = await client.call_tool("joplin_search", {"query": "q", "limit": 50})
    assert result.data == []
