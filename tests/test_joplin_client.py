"""Tests for the Joplin REST API client."""

import httpx
import respx

from second_brain_joplin.joplin_client import JoplinClient


def test_base_url_is_normalized():
    client = JoplinClient(base_url="http://localhost:41184/", token="tok")
    assert client.base_url == "http://localhost:41184"
    assert client._params == {"token": "tok"}


@respx.mock
async def test_ping_ok():
    respx.get("http://localhost:41184/ping").mock(
        return_value=httpx.Response(200, text="JoplinClipperServer")
    )
    client = JoplinClient(base_url="http://localhost:41184", token="tok")
    assert await client.ping() is True


@respx.mock
async def test_ping_unexpected_body():
    respx.get("http://localhost:41184/ping").mock(return_value=httpx.Response(200, text="nope"))
    client = JoplinClient(base_url="http://localhost:41184", token="tok")
    assert await client.ping() is False


@respx.mock
async def test_ping_connect_error():
    respx.get("http://localhost:41184/ping").mock(side_effect=httpx.ConnectError("boom"))
    client = JoplinClient(base_url="http://localhost:41184", token="tok")
    assert await client.ping() is False
