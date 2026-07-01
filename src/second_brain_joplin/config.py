"""Runtime configuration for the Joplin MCP server."""

import os

from pydantic import BaseModel, field_validator

DEFAULT_BASE_URL = "http://localhost:41184"
DEFAULT_TIMEOUT = 10.0


class Settings(BaseModel):
    """Connection settings for the Joplin Data API.

    Read from the environment via :meth:`from_env`. The token may be empty at
    startup so that ``serve`` boots without Joplin configured; a missing token
    surfaces as a friendly error on the first API call, not at import time.
    """

    joplin_base_url: str = DEFAULT_BASE_URL
    joplin_api_token: str = ""
    request_timeout: float = DEFAULT_TIMEOUT

    @field_validator("joplin_base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from ``JOPLIN_BASE_URL`` / ``JOPLIN_API_TOKEN``."""
        return cls(
            joplin_base_url=os.environ.get("JOPLIN_BASE_URL", DEFAULT_BASE_URL),
            joplin_api_token=os.environ.get("JOPLIN_API_TOKEN", ""),
        )
