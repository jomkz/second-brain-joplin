"""Tests for Settings configuration."""

from pathlib import Path

import pytest

from second_brain_joplin.config import (
    DEFAULT_BASE_URL,
    DEFAULT_EMBEDDING_BACKEND,
    DEFAULT_TIMEOUT,
    DEFAULT_VECTOR_STORE,
    Settings,
    default_index_dir,
)

SBJ_VARS = [
    "SBJ_EMBEDDING_BACKEND",
    "SBJ_EMBEDDING_MODEL",
    "SBJ_VECTOR_STORE",
    "SBJ_INDEX_DIR",
    "SBJ_SEMANTIC_AUTO_SYNC",
]


def test_defaults() -> None:
    settings = Settings()
    assert settings.joplin_base_url == DEFAULT_BASE_URL
    assert settings.joplin_api_token == ""
    assert settings.request_timeout == DEFAULT_TIMEOUT
    assert settings.embedding_backend == DEFAULT_EMBEDDING_BACKEND
    assert settings.embedding_model == ""
    assert settings.vector_store == DEFAULT_VECTOR_STORE
    assert settings.semantic_auto_sync is True


def test_trailing_slash_is_stripped() -> None:
    settings = Settings(joplin_base_url="http://example:9999/")
    assert settings.joplin_base_url == "http://example:9999"


def test_from_env_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOPLIN_API_TOKEN", "secret")
    monkeypatch.setenv("JOPLIN_BASE_URL", "http://example:9999/")
    settings = Settings.from_env()
    assert settings.joplin_api_token == "secret"
    assert settings.joplin_base_url == "http://example:9999"


def test_from_env_defaults_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JOPLIN_API_TOKEN", raising=False)
    monkeypatch.delenv("JOPLIN_BASE_URL", raising=False)
    settings = Settings.from_env()
    assert settings.joplin_base_url == DEFAULT_BASE_URL
    assert settings.joplin_api_token == ""


def test_from_env_reads_semantic_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SBJ_EMBEDDING_BACKEND", "sentence-transformers")
    monkeypatch.setenv("SBJ_EMBEDDING_MODEL", "BAAI/bge-m3")
    monkeypatch.setenv("SBJ_VECTOR_STORE", "chroma")
    monkeypatch.setenv("SBJ_INDEX_DIR", "/tmp/custom-index")
    monkeypatch.setenv("SBJ_SEMANTIC_AUTO_SYNC", "false")
    settings = Settings.from_env()
    assert settings.embedding_backend == "sentence-transformers"
    assert settings.embedding_model == "BAAI/bge-m3"
    assert settings.vector_store == "chroma"
    assert settings.semantic_index_dir == "/tmp/custom-index"
    assert settings.semantic_auto_sync is False


def test_from_env_semantic_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in SBJ_VARS:
        monkeypatch.delenv(var, raising=False)
    settings = Settings.from_env()
    assert settings.embedding_backend == DEFAULT_EMBEDDING_BACKEND
    assert settings.vector_store == DEFAULT_VECTOR_STORE
    assert settings.semantic_index_dir == default_index_dir()
    assert settings.semantic_auto_sync is True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1", True), ("yes", True), ("ON", True), ("0", False), ("no", False), ("", False)],
)
def test_auto_sync_bool_parsing(monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool) -> None:
    monkeypatch.setenv("SBJ_SEMANTIC_AUTO_SYNC", raw)
    assert Settings.from_env().semantic_auto_sync is expected


def test_default_index_dir_uses_xdg_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", "/xdg/data")
    assert default_index_dir() == "/xdg/data/second-brain-joplin/index"


def test_default_index_dir_falls_back_to_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/home/tester")))
    assert default_index_dir() == "/home/tester/.local/share/second-brain-joplin/index"
