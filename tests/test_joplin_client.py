"""Tests for the Joplin REST API client."""

import httpx
import pytest
import respx

from second_brain_joplin.config import Settings
from second_brain_joplin.errors import (
    JoplinAPIError,
    JoplinAuthError,
    JoplinConnectionError,
    JoplinNotFoundError,
)
from second_brain_joplin.joplin_client import JoplinClient

BASE_URL = "http://localhost:41184"


def _page(request: httpx.Request, pages: dict[str, httpx.Response]) -> httpx.Response:
    """Return a page response keyed by the ``page`` query param."""
    return pages[request.url.params.get("page", "1")]


def test_base_url_is_normalized():
    client = JoplinClient(Settings(joplin_base_url=f"{BASE_URL}/", joplin_api_token="tok"))
    assert client.base_url == BASE_URL


@respx.mock
async def test_ping_ok(client):
    respx.get(f"{BASE_URL}/ping").mock(return_value=httpx.Response(200, text="JoplinClipperServer"))
    assert await client.ping() is True


@respx.mock
async def test_ping_unexpected_body(client):
    respx.get(f"{BASE_URL}/ping").mock(return_value=httpx.Response(200, text="nope"))
    assert await client.ping() is False


@respx.mock
async def test_ping_connect_error(client):
    respx.get(f"{BASE_URL}/ping").mock(side_effect=httpx.ConnectError("boom"))
    assert await client.ping() is False


@respx.mock
async def test_get_folders_follows_pagination(client):
    pages = {
        "1": httpx.Response(200, json={"items": [{"id": "a"}], "has_more": True}),
        "2": httpx.Response(200, json={"items": [{"id": "b"}], "has_more": False}),
    }
    respx.get(f"{BASE_URL}/folders").mock(side_effect=lambda req: _page(req, pages))
    folders = await client.get_folders()
    assert [f["id"] for f in folders] == ["a", "b"]


@respx.mock
async def test_search_respects_limit(client):
    respx.get(f"{BASE_URL}/search").mock(
        return_value=httpx.Response(
            200, json={"items": [{"id": str(i)} for i in range(10)], "has_more": True}
        )
    )
    hits = await client.search("q", limit=3)
    assert len(hits) == 3


@respx.mock
async def test_search_empty_results(client):
    respx.get(f"{BASE_URL}/search").mock(
        return_value=httpx.Response(200, json={"items": [], "has_more": False})
    )
    assert await client.search("nomatch", limit=10) == []


@respx.mock
async def test_get_note_ok(client):
    respx.get(f"{BASE_URL}/notes/abc").mock(
        return_value=httpx.Response(200, json={"id": "abc", "title": "T", "body": "B"})
    )
    note = await client.get_note("abc")
    assert note["title"] == "T"


@respx.mock
async def test_get_note_not_found_raises(client):
    respx.get(f"{BASE_URL}/notes/missing").mock(return_value=httpx.Response(404))
    with pytest.raises(JoplinNotFoundError):
        await client.get_note("missing")


@respx.mock
async def test_auth_error_raises(client):
    respx.get(f"{BASE_URL}/notes/x").mock(return_value=httpx.Response(403))
    with pytest.raises(JoplinAuthError):
        await client.get_note("x")


@respx.mock
async def test_api_error_raises(client):
    respx.get(f"{BASE_URL}/notes/x").mock(return_value=httpx.Response(500))
    with pytest.raises(JoplinAPIError):
        await client.get_note("x")


@respx.mock
async def test_connect_error_raises(client):
    respx.get(f"{BASE_URL}/notes/x").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(JoplinConnectionError):
        await client.get_note("x")


@respx.mock
async def test_create_note_not_implemented(client):
    with pytest.raises(NotImplementedError):
        await client.create_note("t", "b", "n")
