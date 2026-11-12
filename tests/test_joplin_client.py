"""Tests for the Joplin REST API client."""

import json

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


def test_base_url_is_normalized() -> None:
    client = JoplinClient(Settings(joplin_base_url=f"{BASE_URL}/", joplin_api_token="tok"))
    assert client.base_url == BASE_URL


@respx.mock
async def test_ping_ok(client: JoplinClient) -> None:
    respx.get(f"{BASE_URL}/ping").mock(return_value=httpx.Response(200, text="JoplinClipperServer"))
    assert await client.ping() is True


@respx.mock
async def test_ping_unexpected_body(client: JoplinClient) -> None:
    respx.get(f"{BASE_URL}/ping").mock(return_value=httpx.Response(200, text="nope"))
    assert await client.ping() is False


@respx.mock
async def test_ping_connect_error(client: JoplinClient) -> None:
    respx.get(f"{BASE_URL}/ping").mock(side_effect=httpx.ConnectError("boom"))
    assert await client.ping() is False


@respx.mock
async def test_get_folders_follows_pagination(client: JoplinClient) -> None:
    pages = {
        "1": httpx.Response(200, json={"items": [{"id": "a"}], "has_more": True}),
        "2": httpx.Response(200, json={"items": [{"id": "b"}], "has_more": False}),
    }
    respx.get(f"{BASE_URL}/folders").mock(side_effect=lambda req: _page(req, pages))
    folders = await client.get_folders()
    assert [f["id"] for f in folders] == ["a", "b"]


@respx.mock
async def test_search_respects_limit(client: JoplinClient) -> None:
    respx.get(f"{BASE_URL}/search").mock(
        return_value=httpx.Response(
            200, json={"items": [{"id": str(i)} for i in range(10)], "has_more": True}
        )
    )
    hits = await client.search("q", limit=3)
    assert len(hits) == 3


@respx.mock
async def test_search_empty_results(client: JoplinClient) -> None:
    respx.get(f"{BASE_URL}/search").mock(
        return_value=httpx.Response(200, json={"items": [], "has_more": False})
    )
    assert await client.search("nomatch", limit=10) == []


@respx.mock
async def test_list_note_versions_follows_pagination(client: JoplinClient) -> None:
    pages = {
        "1": httpx.Response(
            200,
            json={"items": [{"id": "a", "updated_time": 111}], "has_more": True},
        ),
        "2": httpx.Response(
            200,
            json={"items": [{"id": "b", "updated_time": 222}], "has_more": False},
        ),
    }
    respx.get(f"{BASE_URL}/notes").mock(side_effect=lambda req: _page(req, pages))
    notes = await client.list_note_versions()
    assert [(n["id"], n["updated_time"]) for n in notes] == [("a", 111), ("b", 222)]


@respx.mock
async def test_get_note_ok(client: JoplinClient) -> None:
    respx.get(f"{BASE_URL}/notes/abc").mock(
        return_value=httpx.Response(200, json={"id": "abc", "title": "T", "body": "B"})
    )
    note = await client.get_note("abc")
    assert note["title"] == "T"


@respx.mock
async def test_get_note_not_found_raises(client: JoplinClient) -> None:
    respx.get(f"{BASE_URL}/notes/missing").mock(return_value=httpx.Response(404))
    with pytest.raises(JoplinNotFoundError):
        await client.get_note("missing")


@respx.mock
async def test_auth_error_raises(client: JoplinClient) -> None:
    respx.get(f"{BASE_URL}/notes/x").mock(return_value=httpx.Response(403))
    with pytest.raises(JoplinAuthError):
        await client.get_note("x")


@respx.mock
async def test_api_error_raises(client: JoplinClient) -> None:
    respx.get(f"{BASE_URL}/notes/x").mock(return_value=httpx.Response(500))
    with pytest.raises(JoplinAPIError):
        await client.get_note("x")


@respx.mock
async def test_connect_error_raises(client: JoplinClient) -> None:
    respx.get(f"{BASE_URL}/notes/x").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(JoplinConnectionError):
        await client.get_note("x")


@respx.mock
async def test_timeout_raises_connection_error_naming_the_wait(client: JoplinClient) -> None:
    respx.get(f"{BASE_URL}/notes/x").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(JoplinConnectionError, match="didn't answer .* within 10 seconds"):
        await client.get_note("x")


@respx.mock
async def test_other_transport_errors_raise_connection_error(client: JoplinClient) -> None:
    respx.get(f"{BASE_URL}/notes/x").mock(side_effect=httpx.RemoteProtocolError("reset"))
    with pytest.raises(JoplinConnectionError, match="unreachable"):
        await client.get_note("x")


@respx.mock
async def test_ping_timeout_is_down(client: JoplinClient) -> None:
    respx.get(f"{BASE_URL}/ping").mock(side_effect=httpx.ConnectTimeout("slow"))
    assert await client.ping() is False


def _numbered_pages(per_page: int, total: int) -> dict[str, httpx.Response]:
    """``total`` items ``{"id": "0"}``, ``{"id": "1"}``, ... split into pages."""
    pages = {}
    for start in range(0, total, per_page):
        items = [{"id": str(i), "updated_time": 1000 - i} for i in range(start, start + per_page)]
        pages[str(start // per_page + 1)] = httpx.Response(
            200, json={"items": items, "has_more": start + per_page < total}
        )
    return pages


@respx.mock
async def test_search_with_keep_pages_on_until_the_limit_is_filled(client: JoplinClient) -> None:
    pages = _numbered_pages(per_page=3, total=12)
    route = respx.get(f"{BASE_URL}/search").mock(side_effect=lambda req: _page(req, pages))
    hits = await client.search("q", limit=4, keep=lambda item: int(item["id"]) % 2 == 1)
    assert [h["id"] for h in hits] == ["1", "3", "5", "7"]  # Joplin's order is kept
    assert route.call_count == 3  # stopped on the page that filled the limit


@respx.mock
async def test_search_with_keep_ends_when_joplin_runs_out(client: JoplinClient) -> None:
    pages = _numbered_pages(per_page=3, total=6)
    route = respx.get(f"{BASE_URL}/search").mock(side_effect=lambda req: _page(req, pages))
    hits = await client.search("q", limit=10, keep=lambda item: item["id"] == "4")
    assert [h["id"] for h in hits] == ["4"]
    assert route.call_count == 2


@respx.mock
async def test_search_asks_for_the_notebook_of_each_hit(client: JoplinClient) -> None:
    route = respx.get(f"{BASE_URL}/search").mock(
        return_value=httpx.Response(200, json={"items": [], "has_more": False})
    )
    await client.search("q", limit=1)
    assert "parent_id" in route.calls.last.request.url.params["fields"].split(",")


@respx.mock
async def test_get_recent_stops_at_the_first_item_older_than_since(client: JoplinClient) -> None:
    pages = _numbered_pages(per_page=3, total=12)  # updated_time 1000, 999, 998, ...
    route = respx.get(f"{BASE_URL}/notes").mock(side_effect=lambda req: _page(req, pages))
    notes = await client.get_recent(50, since_ms=996)
    assert [n["updated_time"] for n in notes] == [1000, 999, 998, 997, 996]
    assert route.call_count == 2  # the second page held the first too-old note


@respx.mock
async def test_get_recent_counts_only_kept_items_toward_the_limit(client: JoplinClient) -> None:
    pages = _numbered_pages(per_page=3, total=12)
    respx.get(f"{BASE_URL}/notes").mock(side_effect=lambda req: _page(req, pages))
    notes = await client.get_recent(2, keep=lambda item: int(item["id"]) >= 4)
    assert [n["id"] for n in notes] == ["4", "5"]


@respx.mock
async def test_get_recent_treats_a_missing_updated_time_as_too_old(client: JoplinClient) -> None:
    respx.get(f"{BASE_URL}/notes").mock(
        return_value=httpx.Response(
            200, json={"items": [{"id": "a", "updated_time": 5}, {"id": "b"}], "has_more": False}
        )
    )
    assert [n["id"] for n in await client.get_recent(10, since_ms=1)] == ["a"]


@respx.mock
async def test_list_note_versions_asks_for_each_notes_notebook(client: JoplinClient) -> None:
    route = respx.get(f"{BASE_URL}/notes").mock(
        return_value=httpx.Response(200, json={"items": [], "has_more": False})
    )
    await client.list_note_versions()
    assert route.calls.last.request.url.params["fields"] == "id,updated_time,parent_id"


@respx.mock
async def test_create_note_posts_the_note_with_the_callers_id(client: JoplinClient) -> None:
    route = respx.post(f"{BASE_URL}/notes").mock(
        return_value=httpx.Response(200, json={"id": "a" * 32, "created_time": 5})
    )
    created = await client.create_note("a" * 32, "Title", "Body **text**", "b" * 32)
    assert created == {"id": "a" * 32, "created_time": 5}
    request = route.calls.last.request
    assert json.loads(request.content) == {
        "id": "a" * 32,
        "title": "Title",
        "body": "Body **text**",
        "parent_id": "b" * 32,
    }
    assert request.url.params["token"] == "tok"  # the token rides in the URL, as for reads


@respx.mock
async def test_create_note_maps_errors_like_any_other_request(client: JoplinClient) -> None:
    respx.post(f"{BASE_URL}/notes").mock(return_value=httpx.Response(403))
    with pytest.raises(JoplinAuthError):
        await client.create_note("a" * 32, "T", "B", "b" * 32)
    respx.post(f"{BASE_URL}/notes").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(JoplinConnectionError, match="didn't answer"):
        await client.create_note("a" * 32, "T", "B", "b" * 32)


@respx.mock
async def test_note_exists(client: JoplinClient) -> None:
    respx.get(f"{BASE_URL}/notes/{'a' * 32}").mock(
        return_value=httpx.Response(200, json={"id": "a" * 32})
    )
    respx.get(f"{BASE_URL}/notes/{'c' * 32}").mock(return_value=httpx.Response(404))
    assert await client.note_exists("a" * 32) is True
    assert await client.note_exists("c" * 32) is False


@respx.mock
async def test_note_exists_does_not_hide_joplin_being_down(client: JoplinClient) -> None:
    respx.get(f"{BASE_URL}/notes/{'a' * 32}").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(JoplinConnectionError):
        await client.note_exists("a" * 32)


@pytest.mark.parametrize("answer", [httpx.Response(200, text="ok"), httpx.Response(200, json=[1])])
@respx.mock
async def test_create_note_treats_any_2xx_answer_as_created(
    client: JoplinClient, answer: httpx.Response
) -> None:
    respx.post(f"{BASE_URL}/notes").mock(return_value=answer)
    assert await client.create_note("a" * 32, "T", "B", "b" * 32) == {}


@pytest.mark.parametrize(
    ("error", "maybe_sent"),
    [
        (httpx.ConnectError("refused"), False),
        (httpx.ConnectTimeout("no route"), False),
        (httpx.PoolTimeout("no free connection"), False),
        (httpx.ReadTimeout("no answer"), True),
        (httpx.WriteTimeout("stalled"), True),
        (httpx.ReadError("reset"), True),
        (httpx.RemoteProtocolError("garbage"), True),
    ],
)
@respx.mock
async def test_a_connection_error_says_whether_the_request_may_have_been_sent(
    client: JoplinClient, error: Exception, maybe_sent: bool
) -> None:
    respx.post(f"{BASE_URL}/notes").mock(side_effect=error)
    with pytest.raises(JoplinConnectionError) as raised:
        await client.create_note("a" * 32, "T", "B", "b" * 32)
    assert raised.value.maybe_sent is maybe_sent
