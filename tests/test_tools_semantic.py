"""Tests for the semantic MCP tools, driven through a FastMCP client."""

from typing import Any

import httpx
import pytest
import respx
from fakes import FakeEmbedder, FakeVectorIndex
from fastmcp import Client
from fastmcp.exceptions import ToolError

from second_brain_joplin.errors import SemanticUnavailableError
from second_brain_joplin.semantic import backends
from second_brain_joplin.server import mcp

BASE_URL = "http://localhost:41184"


def _attr(obj: object, name: str) -> Any:
    """Read a field whether FastMCP returned a model instance or a dict."""
    return obj[name] if isinstance(obj, dict) else getattr(obj, name)


def _install_fakes(monkeypatch: pytest.MonkeyPatch, index: FakeVectorIndex | None = None) -> None:
    shared_index = index or FakeVectorIndex()
    monkeypatch.setattr(backends, "build_embedder", lambda settings: FakeEmbedder())
    monkeypatch.setattr(backends, "build_vector_index", lambda settings, model_name: shared_index)


def _mock_vault(notes: dict[str, tuple[str, str, int]]) -> None:
    items = [{"id": nid, "updated_time": ut} for nid, (_, _, ut) in notes.items()]
    respx.get(f"{BASE_URL}/notes").mock(
        return_value=httpx.Response(200, json={"items": items, "has_more": False})
    )

    def note_response(request: httpx.Request) -> httpx.Response:
        nid = request.url.path.rsplit("/", 1)[-1]
        title, body, ut = notes[nid]
        return httpx.Response(
            200,
            json={
                "id": nid,
                "title": title,
                "body": body,
                "parent_id": "",
                "created_time": 0,
                "updated_time": ut,
            },
        )

    respx.get(url__regex=rf"{BASE_URL}/notes/[^/?]+").mock(side_effect=note_response)


@respx.mock
async def test_semantic_search_returns_ranked_results(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fakes(monkeypatch)
    _mock_vault(
        {
            "a": ("Apple", "apple banana cherry", 100),
            "b": ("Dog", "dog elephant frog", 100),
        }
    )
    async with Client(mcp) as client:
        result = await client.call_tool("joplin_semantic_search", {"query": "apple", "limit": 5})

    hits = result.data
    assert _attr(hits[0], "id") == "a"
    assert _attr(hits[0], "score") > 0
    assert "apple" in _attr(hits[0], "excerpt").lower()


@respx.mock
async def test_reindex_reports_stats(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fakes(monkeypatch)
    _mock_vault({"a": ("A", "alpha", 100), "b": ("B", "beta", 100)})

    async with Client(mcp) as client:
        result = await client.call_tool("joplin_reindex", {"full": True})

    data = result.data
    assert _attr(data, "added") == 2
    assert _attr(data, "total") == 2
    assert _attr(data, "model") == "fake-model"


@respx.mock
async def test_semantic_search_missing_extra_raises_tool_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(settings: object) -> object:
        raise SemanticUnavailableError("install second-brain-joplin[semantic]")

    monkeypatch.setattr(backends, "build_embedder", boom)

    async with Client(mcp) as client:
        with pytest.raises(ToolError, match="semantic"):
            await client.call_tool("joplin_semantic_search", {"query": "x"})


@respx.mock
async def test_reindex_surfaces_joplin_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fakes(monkeypatch)
    respx.get(f"{BASE_URL}/notes").mock(return_value=httpx.Response(500))

    async with Client(mcp) as client:
        with pytest.raises(ToolError):
            await client.call_tool("joplin_reindex", {})
