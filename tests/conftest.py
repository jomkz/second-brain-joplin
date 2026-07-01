"""Shared test fixtures."""

import pytest

from second_brain_joplin.config import Settings
from second_brain_joplin.joplin_client import JoplinClient

BASE_URL = "http://localhost:41184"


@pytest.fixture
def client() -> JoplinClient:
    """A JoplinClient pointed at the default localhost base URL."""
    return JoplinClient(Settings(joplin_base_url=BASE_URL, joplin_api_token="tok"))
