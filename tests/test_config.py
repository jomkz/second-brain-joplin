"""Tests for Settings configuration."""

import pytest

from second_brain_joplin.config import DEFAULT_BASE_URL, DEFAULT_TIMEOUT, Settings


def test_defaults() -> None:
    settings = Settings()
    assert settings.joplin_base_url == DEFAULT_BASE_URL
    assert settings.joplin_api_token == ""
    assert settings.request_timeout == DEFAULT_TIMEOUT


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
