"""Application context handed to MCP tools via the server lifespan.

Holds the shared Joplin client and settings, and lazily builds the semantic
search service on first use. The optional ML/vector backends are imported only
inside :meth:`AppContext.semantic` (via :mod:`.semantic.backends`), so importing
this module — and therefore starting the server on a base install — never
requires the extras.
"""

from dataclasses import dataclass, field
from typing import cast

from fastmcp import Context

from .config import Settings
from .joplin_client import JoplinClient
from .scope import NotebookScope, WriteTargets, current_scope, current_write_targets
from .semantic.service import SemanticSearchService


@dataclass
class AppContext:
    """Per-server shared state reachable from tools via ``ctx.lifespan_context``."""

    client: JoplinClient
    settings: Settings
    # True in HTTP mode: tools that would run past a remote client's time limit
    # (a full reindex) refuse there and point at the CLI instead.
    remote: bool = False
    _semantic: SemanticSearchService | None = field(default=None, init=False, repr=False)

    async def scope(self) -> NotebookScope:
        """The notebooks a tool may see, resolved against Joplin now (scope.py).

        Raises :class:`NotebookFilterError` when the configured filter doesn't
        resolve; a tool must then refuse rather than show anything.
        """
        return await current_scope(self.client, self.settings)

    async def write_targets(self) -> WriteTargets:
        """The notebooks a note may be created in, resolved against Joplin now.

        Empty when the server is read-only. Raises :class:`NotebookFilterError`
        when the notebook settings don't resolve; the write tool must then refuse.
        """
        return await current_write_targets(self.client, self.settings)

    def semantic(self) -> SemanticSearchService:
        """Return the semantic service, building it (and loading the model) once.

        Raises :class:`SemanticUnavailableError` if the semantic extra is missing
        or misconfigured.
        """
        if self._semantic is None:
            from .semantic import backends

            embedder = backends.build_embedder(self.settings)
            index = backends.build_vector_index(self.settings, embedder.model_name)
            self._semantic = SemanticSearchService(self.client, embedder, index, self.settings)
        return self._semantic


def app_context(ctx: Context) -> AppContext:
    """Fetch the :class:`AppContext` from a FastMCP tool context."""
    return cast(AppContext, ctx.lifespan_context)
