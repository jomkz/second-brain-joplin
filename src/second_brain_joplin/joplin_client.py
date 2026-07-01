"""Joplin Data API client (localhost:41184).

Thin async wrapper around the Joplin Web Clipper REST API. It returns raw API
dicts; shaping into response models and applying business rules (excerpts, day
filtering) is the tool layer's job.

Requires Joplin Desktop running with the Web Clipper service enabled. The token
is available at Tools → Options → Web Clipper.
"""

from typing import Any

import httpx

from .config import Settings
from .errors import (
    JoplinAPIError,
    JoplinAuthError,
    JoplinConnectionError,
    JoplinNotFoundError,
)

JsonDict = dict[str, Any]


class JoplinClient:
    """Async client over the Joplin Data API with typed error mapping."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.joplin_base_url,
            params={"token": settings.joplin_api_token},
            timeout=settings.request_timeout,
        )

    @property
    def base_url(self) -> str:
        return self._settings.joplin_base_url

    async def aclose(self) -> None:
        await self._client.aclose()

    async def ping(self) -> bool:
        """Return True if the Joplin API is reachable and responding."""
        try:
            response = await self._client.get("/ping")
        except httpx.ConnectError:
            return False
        return response.text.strip() == "JoplinClipperServer"

    # -- low-level helpers ---------------------------------------------------

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.is_success:
            return
        status = response.status_code
        if status in (401, 403):
            raise JoplinAuthError(
                "Joplin rejected the request — check that JOPLIN_API_TOKEN is set and "
                "matches the token in Joplin's Web Clipper settings."
            )
        if status == 404:
            raise JoplinNotFoundError("The requested Joplin resource was not found.")
        raise JoplinAPIError(f"Joplin returned an unexpected response (HTTP {status}).")

    async def _get(self, path: str, params: JsonDict | None = None) -> httpx.Response:
        try:
            response = await self._client.get(path, params=params)
        except httpx.ConnectError as exc:
            raise JoplinConnectionError(
                f"Joplin is unreachable at {self.base_url} — is Joplin Desktop running "
                "with the Web Clipper service enabled?"
            ) from exc
        self._raise_for_status(response)
        return response

    async def _get_paginated(
        self, path: str, params: JsonDict | None = None, max_items: int | None = None
    ) -> list[JsonDict]:
        """Follow Joplin's ``has_more``/``page`` pagination and collect items.

        When ``max_items`` is set, stops once that many items are collected —
        useful for endpoints ordered so the earliest pages are the ones we want.
        """
        items: list[JsonDict] = []
        base_params = dict(params or {})
        page = 1
        while True:
            data = (await self._get(path, {**base_params, "page": page})).json()
            items.extend(data.get("items", []))
            if max_items is not None and len(items) >= max_items:
                return items[:max_items]
            if not data.get("has_more"):
                return items
            page += 1

    # -- endpoints -----------------------------------------------------------

    async def get_folders(self) -> list[JsonDict]:
        """Return all notebooks (Joplin folders) with their hierarchy."""
        return await self._get_paginated("/folders", {"fields": "id,title,parent_id"})

    async def get_notes_index(self) -> list[JsonDict]:
        """Return every note's id and parent, for tallying notebook counts."""
        return await self._get_paginated("/notes", {"fields": "id,parent_id"})

    async def list_note_versions(self) -> list[JsonDict]:
        """Return every note's id and ``updated_time`` for incremental sync.

        Cheap (no bodies): used to detect which notes changed since the last
        embedding sync.
        """
        return await self._get_paginated("/notes", {"fields": "id,updated_time"})

    async def get_note(self, note_id: str) -> JsonDict:
        """Return a single note including its full markdown body."""
        params = {"fields": "id,title,body,parent_id,created_time,updated_time"}
        data: JsonDict = (await self._get(f"/notes/{note_id}", params)).json()
        return data

    async def search(self, query: str, limit: int) -> list[JsonDict]:
        """Keyword-search notes, returning up to ``limit`` raw hits."""
        return await self._get_paginated(
            "/search",
            {"query": query, "type": "note", "fields": "id,title,body"},
            max_items=limit,
        )

    async def get_recent(self, limit: int) -> list[JsonDict]:
        """Return the ``limit`` most-recently-updated notes (newest first)."""
        return await self._get_paginated(
            "/notes",
            {
                "fields": "id,title,updated_time",
                "order_by": "updated_time",
                "order_dir": "DESC",
            },
            max_items=limit,
        )

    async def create_note(self, title: str, body: str, notebook_id: str) -> JsonDict:
        # Real implementation lands with the human-gated write flow (issue #10).
        raise NotImplementedError
