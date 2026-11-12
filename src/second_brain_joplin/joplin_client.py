"""Joplin Data API client (localhost:41184).

Thin async wrapper around the Joplin Web Clipper REST API. It returns raw API
dicts; shaping into response models and applying business rules (excerpts, day
filtering, who may write where) is the tool layer's job.

Requires Joplin Desktop running with the Web Clipper service enabled. The token
is available at Tools → Options → Web Clipper.
"""

from collections.abc import Callable
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
ItemTest = Callable[[JsonDict], bool]

# Failures that happen before a request is on the wire: no connection was made, or
# none was free. Anything else may have reached Joplin.
_NEVER_SENT = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    httpx.UnsupportedProtocol,
)


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
        except httpx.TransportError:  # refused, timed out, or the connection dropped
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
            raise JoplinNotFoundError()
        raise JoplinAPIError(f"Joplin returned an unexpected response (HTTP {status}).")

    async def _request(
        self,
        method: str,
        path: str,
        params: JsonDict | None = None,
        json: JsonDict | None = None,
    ) -> httpx.Response:
        try:
            response = await self._client.request(method, path, params=params, json=json)
        except httpx.TimeoutException as exc:
            raise JoplinConnectionError(
                f"Joplin didn't answer at {self.base_url} within "
                f"{self._settings.request_timeout:g} seconds — is Joplin Desktop running "
                "and responsive?",
                maybe_sent=not isinstance(exc, _NEVER_SENT),
            ) from exc
        except httpx.TransportError as exc:  # refused, reset, DNS, protocol errors
            raise JoplinConnectionError(
                f"Joplin is unreachable at {self.base_url} — is Joplin Desktop running "
                "with the Web Clipper service enabled?",
                maybe_sent=not isinstance(exc, _NEVER_SENT),
            ) from exc
        self._raise_for_status(response)
        return response

    async def _get(self, path: str, params: JsonDict | None = None) -> httpx.Response:
        return await self._request("GET", path, params=params)

    async def _get_paginated(
        self,
        path: str,
        params: JsonDict | None = None,
        *,
        max_items: int | None = None,
        keep: ItemTest | None = None,
        stop: ItemTest | None = None,
    ) -> list[JsonDict]:
        """Follow Joplin's ``has_more``/``page`` pagination and collect items.

        ``keep`` drops the items it answers False for; only kept items count
        toward ``max_items``, so the walk goes on through further pages until
        that many are found or Joplin runs out. That is what lets a filtered
        listing still fill its limit. ``stop`` ends the walk at the first item it
        answers True for (that item is left out), for endpoints ordered so that
        nothing after it can qualify.
        """
        items: list[JsonDict] = []
        base_params = dict(params or {})
        page = 1
        while True:
            data = (await self._get(path, {**base_params, "page": page})).json()
            for item in data.get("items", []):
                if stop is not None and stop(item):
                    return items
                if keep is not None and not keep(item):
                    continue
                items.append(item)
                if max_items is not None and len(items) >= max_items:
                    return items
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
        """Return every note's id, ``updated_time`` and notebook for incremental sync.

        Cheap (no bodies): used to detect which notes changed since the last
        embedding sync, and which the notebook filter lets through.
        """
        return await self._get_paginated("/notes", {"fields": "id,updated_time,parent_id"})

    async def get_note(self, note_id: str) -> JsonDict:
        """Return a single note including its full markdown body."""
        params = {"fields": "id,title,body,parent_id,created_time,updated_time"}
        data: JsonDict = (await self._get(f"/notes/{note_id}", params)).json()
        return data

    async def search(self, query: str, limit: int, keep: ItemTest | None = None) -> list[JsonDict]:
        """Keyword-search notes, returning the first ``limit`` hits ``keep`` lets through."""
        return await self._get_paginated(
            "/search",
            {"query": query, "type": "note", "fields": "id,title,body,parent_id"},
            max_items=limit,
            keep=keep,
        )

    async def get_recent(
        self, limit: int, *, since_ms: int = 0, keep: ItemTest | None = None
    ) -> list[JsonDict]:
        """Return up to ``limit`` notes updated at or after ``since_ms``, newest first.

        The listing is ordered newest first, so the walk stops at the first note
        older than ``since_ms`` instead of paging through the rest of the vault.
        """
        return await self._get_paginated(
            "/notes",
            {
                "fields": "id,title,updated_time,parent_id",
                "order_by": "updated_time",
                "order_dir": "DESC",
            },
            max_items=limit,
            keep=keep,
            stop=lambda note: note.get("updated_time", 0) < since_ms,
        )

    async def note_exists(self, note_id: str) -> bool:
        """True if a note with this id exists (trash and conflicts aside)."""
        try:
            await self._get(f"/notes/{note_id}", {"fields": "id"})
        except JoplinNotFoundError:
            return False
        return True

    async def create_note(self, note_id: str, title: str, body: str, parent_id: str) -> JsonDict:
        """Create a note with a chosen id in the notebook ``parent_id``; return Joplin's note.

        Returns an empty dict if Joplin's answer isn't a JSON object.

        The id is the caller's (32 hexadecimal characters) rather than one Joplin
        makes up, so the caller can tell afterwards whether a request that failed
        on the way back did create the note.
        """
        response = await self._request(
            "POST",
            "/notes",
            json={"id": note_id, "title": title, "body": body, "parent_id": parent_id},
        )
        # Joplin answered 2xx, so the note exists. An answer that isn't the note
        # as a JSON object must not turn that into a failure: the caller knows the id.
        try:
            data = response.json()
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}
