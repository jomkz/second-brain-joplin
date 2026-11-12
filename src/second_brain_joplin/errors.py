"""Typed errors raised by the Joplin client.

Each error carries a human-readable message that the MCP tool layer passes
straight into ``fastmcp.exceptions.ToolError`` so the AI client sees an
actionable explanation.
"""


class JoplinError(Exception):
    """Base class for all Joplin client failures."""


class JoplinConnectionError(JoplinError):
    """Joplin's Web Clipper service could not be reached, or didn't answer.

    ``maybe_sent`` is False when the request provably never left (the connection
    was refused or never opened), and True when it may have reached Joplin and
    only the answer is missing. For a read the difference doesn't matter. For a
    write it is the difference between "nothing happened" and "can't tell".
    """

    def __init__(self, message: str, *, maybe_sent: bool = True) -> None:
        super().__init__(message)
        self.maybe_sent = maybe_sent


class JoplinAuthError(JoplinError):
    """Joplin rejected the request — missing or invalid API token."""


NOT_FOUND_MESSAGE = "The requested Joplin resource was not found."


class JoplinNotFoundError(JoplinError):
    """The requested resource (e.g. a note ID) does not exist.

    Also raised for a note the notebook filter hides. Both cases carry the same
    message, so an answer never tells a caller that a hidden note exists.
    """

    def __init__(self, message: str = NOT_FOUND_MESSAGE) -> None:
        super().__init__(message)


class JoplinAPIError(JoplinError):
    """Joplin returned an unexpected error response."""


NOTEBOOK_FILTER_MESSAGE = (
    "The server's notebook settings (SBJ_NOTEBOOKS, SBJ_EXCLUDE_NOTEBOOKS, "
    "SBJ_WRITE_NOTEBOOKS) don't match Joplin's notebooks, so this is refused until "
    "they are fixed. On the server's machine, `second-brain-joplin notebooks` "
    "shows what is wrong."
)


class NotebookFilterError(Exception):
    """A notebook setting names something Joplin's notebooks don't match.

    The tools it governs refuse while this holds: a filter that can't be resolved
    must not fall back to showing everything, nor a write list to allowing every
    notebook. ``str()`` is the same fixed sentence every time and is safe to hand
    to a remote client. ``detail`` says which variable and entry is wrong; an
    entry can be the title of a notebook the operator wants hidden, so the detail
    is for the operator only (the log, the command line).

    Deliberately not a :class:`JoplinError`: it is a configuration problem, not a
    Joplin API failure.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(NOTEBOOK_FILTER_MESSAGE)
        self.detail = detail


class SemanticUnavailableError(Exception):
    """Semantic search cannot run — the optional dependencies are missing.

    Raised when a semantic backend (embedder or vector store) cannot be built,
    typically because the ``second-brain-joplin[semantic]`` extra is not
    installed. The message tells the user how to enable it. Deliberately not a
    :class:`JoplinError`: it is a local configuration problem, not a Joplin API
    failure.
    """
