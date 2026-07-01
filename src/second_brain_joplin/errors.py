"""Typed errors raised by the Joplin client.

Each error carries a human-readable message that the MCP tool layer passes
straight into ``fastmcp.exceptions.ToolError`` so the AI client sees an
actionable explanation.
"""


class JoplinError(Exception):
    """Base class for all Joplin client failures."""


class JoplinConnectionError(JoplinError):
    """Joplin's Web Clipper service could not be reached."""


class JoplinAuthError(JoplinError):
    """Joplin rejected the request — missing or invalid API token."""


class JoplinNotFoundError(JoplinError):
    """The requested resource (e.g. a note ID) does not exist."""


class JoplinAPIError(JoplinError):
    """Joplin returned an unexpected error response."""


class SemanticUnavailableError(Exception):
    """Semantic search cannot run — the optional dependencies are missing.

    Raised when a semantic backend (embedder or vector store) cannot be built,
    typically because the ``second-brain-joplin[semantic]`` extra is not
    installed. The message tells the user how to enable it. Deliberately not a
    :class:`JoplinError`: it is a local configuration problem, not a Joplin API
    failure.
    """
