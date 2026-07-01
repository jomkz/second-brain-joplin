"""Tests for AppContext's lazy semantic-service wiring."""

import pytest
from fakes import FakeEmbedder, FakeVectorIndex

from second_brain_joplin.config import Settings
from second_brain_joplin.context import AppContext
from second_brain_joplin.errors import SemanticUnavailableError
from second_brain_joplin.joplin_client import JoplinClient
from second_brain_joplin.semantic import backends
from second_brain_joplin.semantic.service import SemanticSearchService

BASE_URL = "http://localhost:41184"


def _app_context() -> AppContext:
    settings = Settings(joplin_base_url=BASE_URL, joplin_api_token="tok")
    return AppContext(client=JoplinClient(settings), settings=settings)


def test_semantic_builds_once_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"embedder": 0, "index": 0}

    def fake_build_embedder(settings: Settings) -> FakeEmbedder:
        calls["embedder"] += 1
        return FakeEmbedder()

    def fake_build_index(settings: Settings, model_name: str) -> FakeVectorIndex:
        calls["index"] += 1
        return FakeVectorIndex()

    monkeypatch.setattr(backends, "build_embedder", fake_build_embedder)
    monkeypatch.setattr(backends, "build_vector_index", fake_build_index)

    ctx = _app_context()
    first = ctx.semantic()
    second = ctx.semantic()

    assert isinstance(first, SemanticSearchService)
    assert first is second  # cached
    assert calls == {"embedder": 1, "index": 1}  # builders invoked once


def test_semantic_propagates_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(settings: Settings) -> FakeEmbedder:
        raise SemanticUnavailableError("install the extra")

    monkeypatch.setattr(backends, "build_embedder", boom)

    with pytest.raises(SemanticUnavailableError):
        _app_context().semantic()
