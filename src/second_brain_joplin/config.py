"""Runtime configuration for the Joplin MCP server."""

import os
from pathlib import Path

from pydantic import BaseModel, field_validator

DEFAULT_BASE_URL = "http://localhost:41184"
DEFAULT_TIMEOUT = 10.0

DEFAULT_EMBEDDING_BACKEND = "fastembed"
DEFAULT_VECTOR_STORE = "sqlite-vec"


def default_index_dir() -> str:
    """Return the default on-disk location for the semantic index.

    Follows the XDG Base Directory spec: ``$XDG_DATA_HOME/second-brain-joplin/index``
    when set, otherwise ``~/.local/share/second-brain-joplin/index``.
    """
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return str(base / "second-brain-joplin" / "index")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    """Connection and semantic-search settings for the Joplin MCP server.

    Connection settings are read from ``JOPLIN_*`` env vars; semantic-search
    settings from ``SBJ_*``. The token may be empty at startup so that ``serve``
    boots without Joplin configured; a missing token surfaces as a friendly
    error on the first API call, not at import time.
    """

    joplin_base_url: str = DEFAULT_BASE_URL
    joplin_api_token: str = ""
    request_timeout: float = DEFAULT_TIMEOUT

    embedding_backend: str = DEFAULT_EMBEDDING_BACKEND
    embedding_model: str = ""
    vector_store: str = DEFAULT_VECTOR_STORE
    semantic_index_dir: str = ""
    semantic_auto_sync: bool = True

    @field_validator("joplin_base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from ``JOPLIN_*`` / ``SBJ_*`` environment variables."""
        return cls(
            joplin_base_url=os.environ.get("JOPLIN_BASE_URL", DEFAULT_BASE_URL),
            joplin_api_token=os.environ.get("JOPLIN_API_TOKEN", ""),
            embedding_backend=os.environ.get("SBJ_EMBEDDING_BACKEND", DEFAULT_EMBEDDING_BACKEND),
            embedding_model=os.environ.get("SBJ_EMBEDDING_MODEL", ""),
            vector_store=os.environ.get("SBJ_VECTOR_STORE", DEFAULT_VECTOR_STORE),
            semantic_index_dir=os.environ.get("SBJ_INDEX_DIR", "") or default_index_dir(),
            semantic_auto_sync=_env_bool("SBJ_SEMANTIC_AUTO_SYNC", True),
        )
