"""second-brain-joplin: MCP server for Joplin knowledge bases."""

import os

__version__ = "1.0.1"

# FastMCP, the library underneath, has settings of its own (FASTMCP_*), and when it
# is first imported it reads them from a `.env` in the working directory. For an
# MCP server the working directory is whatever project the client has open, and
# those settings include the transport: a project's `.env` must not be able to
# turn a local stdio server into an HTTP one. Naming an env file that isn't a
# file stops the read. It has to happen here, before anything imports fastmcp,
# and it leaves alone a FASTMCP_ENV_FILE the operator set on purpose.
os.environ.setdefault("FASTMCP_ENV_FILE", os.devnull)
