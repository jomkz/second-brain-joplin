"""MCP tool annotations shared by the tool modules.

Clients use these hints, e.g. to skip a confirmation prompt for a read-only tool.
"""

from mcp.types import ToolAnnotations

# Reads Joplin, changes nothing, and touches nothing beyond this machine's Joplin.
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)

# Updates the local search index only: never Joplin, never deletes a note, and
# running it twice leaves the same index.
LOCAL_INDEX_WRITE = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)

# Adds one new note to Joplin. It never changes or deletes anything that exists,
# so it is not destructive; calling it twice makes two notes, so not idempotent.
CREATES_NOTE = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False
)

# Tool metadata Claude Code honours: prompt the user on every call of this tool,
# with no "don't ask again", whatever allow rules or permission mode are in force
# (Claude Code docs, "Require approval for a specific tool"). Other clients ignore it.
ASK_EVERY_TIME = {"anthropic/requiresUserInteraction": True}
