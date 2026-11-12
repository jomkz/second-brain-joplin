"""Turning a failure inside a tool into the error an MCP client sees."""

import logging

from fastmcp.exceptions import ToolError

from ..errors import NotebookFilterError

logger = logging.getLogger("second_brain_joplin.tools")


def tool_error(exc: Exception) -> ToolError:
    """The ``ToolError`` for ``exc``, carrying its message to the client.

    A notebook filter that doesn't resolve also gets a log line with the detail.
    The client is told only that the filter is wrong: the detail can hold the
    title of a notebook the operator wants hidden.
    """
    if isinstance(exc, NotebookFilterError):
        logger.warning("the notebook filter doesn't resolve: %s", exc.detail)
    return ToolError(str(exc))
