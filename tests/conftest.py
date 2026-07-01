"""Shared test fixtures."""

import pytest

from second_brain_joplin import server


@pytest.fixture(autouse=True)
def reset_client_singleton():
    """Reset the module-level Joplin client between tests.

    ``server._get_client`` memoizes a client in a module global; without this
    the ``_get_client`` tests would leak state and become order-dependent.
    """
    server._client = None
    yield
    server._client = None
