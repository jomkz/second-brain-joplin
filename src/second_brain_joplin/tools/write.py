"""The write tool: creating a note, and only that.

Registered only when the operator has said where notes may go
(``SBJ_WRITE_NOTEBOOKS``); without it the server is read-only and a client can't
even see a write tool. What the tool can do is deliberately narrow: add one new
note to a notebook on that list. It never edits, moves or deletes anything.

The human check on each note is the client's own approval prompt for this call,
which is why the call carries the whole note in readable form (the notebook by
name, the title, the text): what the person approves is what gets written. This
server can't put its own question to the person on every client, so it doesn't
pretend to; it limits where a note can land and leaves a record of each one.

Requests get repeated (a client that timed out, a model trying once more), so the
tool remembers for a few minutes which note it sent (recent.py): the same note
asked for again is found, not made twice.
"""

import logging
import uuid
from typing import Annotated

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from ..audit import caller_id
from ..context import app_context
from ..errors import JoplinAuthError, JoplinConnectionError, JoplinError, NotebookFilterError
from ..joplin_client import JoplinClient
from ..models import MAX_NOTE_CHARS, MAX_TITLE_CHARS, CreatedNote, epoch_ms_to_iso
from ..recent import note_key
from ..scope import ID_RE, WriteTargets
from .annotations import ASK_EVERY_TIME, CREATES_NOTE
from .failure import tool_error

audit_logger = logging.getLogger("second_brain_joplin.audit")

# How many writable notebooks a refusal names before it points at joplin_overview.
REFUSAL_LISTS = 20

WRITES_OFF_MESSAGE = (
    "Note creation is off on this server: its operator hasn't listed any notebook "
    "that may receive notes (SBJ_WRITE_NOTEBOOKS)."
)


def _refusal(targets: WriteTargets) -> ToolError:
    """The one answer for any notebook a note can't go into.

    The same whether the notebook is hidden, doesn't exist or is simply not on
    the list, so it never tells a caller that a hidden notebook exists. It names
    the notebooks that can receive notes, which the caller may see anyway.
    """
    notebooks = sorted(targets.titles.items(), key=lambda item: (item[1].casefold(), item[0]))
    allowed = "; ".join(
        f"{title!r} ({notebook_id})" for notebook_id, title in notebooks[:REFUSAL_LISTS]
    )
    more = len(notebooks) - REFUSAL_LISTS
    if more > 0:
        allowed += f"; and {more} more"
    return ToolError(
        f"A note can't be created in that notebook. Notebooks that can receive notes: {allowed}"
    )


def resolve_target(notebook: str, targets: WriteTargets) -> tuple[str, str]:
    """The (id, title) of the writable notebook ``notebook`` names, by id or exact title."""
    if not targets.titles:
        raise ToolError(WRITES_OFF_MESSAGE)
    wanted = notebook.strip()
    if ID_RE.fullmatch(wanted):
        title = targets.title_of(wanted.lower())
        if title is None:
            raise _refusal(targets)
        return wanted.lower(), title
    matches = [notebook_id for notebook_id, title in targets.titles.items() if title == wanted]
    if len(matches) != 1:  # none, or a title two writable notebooks share: use the id
        raise _refusal(targets)
    return matches[0], wanted


def clean_title(title: str) -> str:
    """The title as Joplin will show it: trimmed, on one line, and not empty."""
    cleaned = " ".join(title.split())
    if not cleaned:
        raise ToolError("A note needs a title.")
    return cleaned


def register(mcp: FastMCP) -> None:
    """Register the write tool on the given FastMCP server."""

    @mcp.tool(annotations=CREATES_NOTE, meta=ASK_EVERY_TIME)
    async def joplin_create_note(
        ctx: Context,
        title: Annotated[
            str,
            Field(
                min_length=1,
                max_length=MAX_TITLE_CHARS,
                description="The note's title, on one line.",
            ),
        ],
        body: Annotated[
            str,
            Field(max_length=MAX_NOTE_CHARS, description="The note's text, in markdown."),
        ],
        notebook: Annotated[
            str,
            Field(
                min_length=1,
                max_length=MAX_TITLE_CHARS,
                description="The notebook to put the note in: its exact title, or its id.",
            ),
        ],
    ) -> CreatedNote:
        """Create a new note in Joplin, in a notebook that accepts new notes.

        Use it only for a note the user asked for, and first tell them the
        notebook, the title and what the note will say. It adds a note and
        nothing else: it can't change, move or delete a note.
        """
        app = app_context(ctx)
        note_title = clean_title(title)
        try:
            targets = await app.write_targets()
        except (JoplinError, NotebookFilterError) as exc:
            raise tool_error(exc) from exc
        notebook_id, notebook_title = resolve_target(notebook, targets)

        def done(note_id: str, created_time: object = None, *, repeat: bool = False) -> CreatedNote:
            when = epoch_ms_to_iso(created_time) if isinstance(created_time, int) else None
            return CreatedNote(
                id=note_id,
                title=note_title,
                notebook_id=notebook_id,
                notebook=notebook_title,
                created_time=when,
                already_created=repeat,
            )

        # A repeat of a request made a moment ago (a retry after a timeout, say)
        # gets the note that request made, not a second copy.
        key = note_key(notebook_id, note_title, body)
        earlier = app.recent_notes.get(key)
        if earlier is not None:
            try:
                if await app.client.note_exists(earlier):
                    return done(earlier, repeat=True)
            except JoplinError as exc:
                raise tool_error(exc) from exc

        # The id is ours, not Joplin's, so a request whose answer goes missing can
        # be looked up afterwards. Ids only in the log: a title is note content.
        note_id = uuid.uuid4().hex
        who = caller_id()

        def record(what: str, level: int = logging.INFO) -> None:
            audit_logger.log(
                level, "note %s id=%s notebook=%s caller=%s", what, note_id, notebook_id, who
            )

        def failed(exc: JoplinError) -> ToolError:
            """Nothing was created: say why, and forget the id."""
            app.recent_notes.forget(key)
            record("create failed")
            return tool_error(exc)

        def unconfirmed(exc: JoplinError) -> ToolError:
            """Can't tell. The id stays remembered, so a repeat looks for it first."""
            record("create unconfirmed", logging.WARNING)
            return ToolError(
                f"{exc} The note may or may not have been created: look in Joplin, or try "
                "again in a moment (a repeat of this request won't make a second copy)."
            )

        app.recent_notes.put(key, note_id)
        record("create sent")
        try:
            created = await app.client.create_note(note_id, note_title, body, notebook_id)
        except JoplinAuthError as exc:
            raise failed(exc) from exc
        except JoplinConnectionError as exc:
            if not exc.maybe_sent:  # it never left this machine
                raise failed(exc) from exc
            # Sent, but no answer. If the note isn't there, Joplin may still be
            # saving it, so "not there" is not yet "not created".
            if not await _landed(app.client, note_id):
                raise unconfirmed(exc) from exc
            created = {"id": note_id}
        except JoplinError as exc:  # Joplin answered, and the answer was an error
            landed = await _landed(app.client, note_id)
            if landed is None:
                raise unconfirmed(exc) from exc
            if not landed:
                raise failed(exc) from exc
            created = {"id": note_id}

        created_id = str(created.get("id") or note_id)
        if created_id != note_id:  # Joplin chose an id of its own after all
            app.recent_notes.put(key, created_id)
            note_id = created_id
        record("created")
        return done(note_id, created.get("created_time"))


async def _landed(client: JoplinClient, note_id: str) -> bool | None:
    """Whether a note we sent exists in Joplin; None if Joplin won't say."""
    try:
        return await client.note_exists(note_id)
    except JoplinError:
        return None
