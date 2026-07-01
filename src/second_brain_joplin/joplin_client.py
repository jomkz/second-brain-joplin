"""Joplin Data API client (localhost:41184)."""

import httpx


class JoplinClient:
    """Thin wrapper around the Joplin REST API.

    Requires Joplin Desktop running with Web Clipper service enabled.
    Token is available at Tools → Options → Web Clipper.
    """

    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._params = {"token": token}

    async def ping(self) -> bool:
        """Return True if the Joplin API is reachable."""
        async with httpx.AsyncClient() as client:
            try:
                r = await client.get(f"{self.base_url}/ping", params=self._params, timeout=3)
                return r.text.strip() == "JoplinClipperServer"
            except httpx.ConnectError:
                return False

    # Remaining methods are stubs — see GitHub issues #4–#8, #10 for
    # implementation. The v0.1 MCP tools short-circuit with a "not implemented"
    # payload before reaching these, so raising here is never hit in v0.1.

    async def get_notebooks(self) -> list[dict]:
        raise NotImplementedError

    async def get_note(self, note_id: str) -> dict:
        raise NotImplementedError

    async def search(self, query: str) -> list[dict]:
        raise NotImplementedError

    async def get_recent(self, days: int) -> list[dict]:
        raise NotImplementedError

    async def create_note(self, title: str, body: str, notebook_id: str) -> dict:
        raise NotImplementedError
