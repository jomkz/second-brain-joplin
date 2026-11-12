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


def _env_list(name: str) -> tuple[str, ...]:
    """A comma-separated variable as its entries, trimmed, without empty ones."""
    return tuple(entry.strip() for entry in os.environ.get(name, "").split(",") if entry.strip())


class Settings(BaseModel):
    """Connection, notebook-filter and semantic-search settings for the server.

    Connection settings are read from ``JOPLIN_*`` env vars; everything else from
    ``SBJ_*``. The token may be empty at startup so that ``serve`` boots without
    Joplin configured; a missing token surfaces as a friendly error on the first
    API call, not at import time.
    """

    joplin_base_url: str = DEFAULT_BASE_URL
    joplin_api_token: str = ""
    request_timeout: float = DEFAULT_TIMEOUT

    # The notebook filter (scope.py): ids or titles, each covering the notebook and
    # everything under it. Both empty means every notebook is visible.
    notebooks: tuple[str, ...] = ()
    exclude_notebooks: tuple[str, ...] = ()
    # Where a note may be created (scope.py); empty means the server is read-only
    # and registers no write tool at all.
    write_notebooks: tuple[str, ...] = ()

    embedding_backend: str = DEFAULT_EMBEDDING_BACKEND
    embedding_model: str = ""
    vector_store: str = DEFAULT_VECTOR_STORE
    semantic_index_dir: str = ""
    semantic_auto_sync: bool = True

    @field_validator("joplin_base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def notebook_filter_set(self) -> bool:
        """True when ``SBJ_NOTEBOOKS`` or ``SBJ_EXCLUDE_NOTEBOOKS`` names anything."""
        return bool(self.notebooks or self.exclude_notebooks)

    @property
    def writes_enabled(self) -> bool:
        """True when ``SBJ_WRITE_NOTEBOOKS`` names anywhere a note may be created."""
        return bool(self.write_notebooks)

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from ``JOPLIN_*`` / ``SBJ_*`` environment variables."""
        return cls(
            joplin_base_url=os.environ.get("JOPLIN_BASE_URL", DEFAULT_BASE_URL),
            joplin_api_token=os.environ.get("JOPLIN_API_TOKEN", ""),
            notebooks=_env_list("SBJ_NOTEBOOKS"),
            exclude_notebooks=_env_list("SBJ_EXCLUDE_NOTEBOOKS"),
            write_notebooks=_env_list("SBJ_WRITE_NOTEBOOKS"),
            embedding_backend=os.environ.get("SBJ_EMBEDDING_BACKEND", DEFAULT_EMBEDDING_BACKEND),
            embedding_model=os.environ.get("SBJ_EMBEDDING_MODEL", ""),
            vector_store=os.environ.get("SBJ_VECTOR_STORE", DEFAULT_VECTOR_STORE),
            semantic_index_dir=os.environ.get("SBJ_INDEX_DIR", "") or default_index_dir(),
            semantic_auto_sync=_env_bool("SBJ_SEMANTIC_AUTO_SYNC", True),
        )
