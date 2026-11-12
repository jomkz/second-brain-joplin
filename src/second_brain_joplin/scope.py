"""Which notebooks the tools may see, and which may receive a new note.

``SBJ_NOTEBOOKS`` shows only the notebooks it lists; ``SBJ_EXCLUDE_NOTEBOOKS`` hides
the ones it lists. An entry is a notebook id (32 hexadecimal characters, stable
across renames) or a title, and covers that notebook and everything under it.
Hiding wins: a notebook under a hidden one stays hidden whatever else lists it.

``SBJ_WRITE_NOTEBOOKS`` lists, the same way, where a note may be created; ``*``
means any visible notebook. It never reaches past the filter: a notebook that is
hidden can't be written to either.

The filter is resolved against Joplin's notebooks on every call, never cached, so
a notebook created under a visible one is visible at once and one moved under a
hidden one disappears at once. A filter that doesn't resolve (an id no notebook
has, a title two notebooks share) raises :class:`NotebookFilterError` instead of
showing anything: falling back to "everything" is how a typo would expose the
wrong notebooks.
"""

import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from .config import Settings
from .errors import JoplinError, NotebookFilterError
from .joplin_client import JoplinClient, JsonDict

logger = logging.getLogger("second_brain_joplin.scope")

INCLUDE_VAR = "SBJ_NOTEBOOKS"
EXCLUDE_VAR = "SBJ_EXCLUDE_NOTEBOOKS"
WRITE_VAR = "SBJ_WRITE_NOTEBOOKS"
# In SBJ_WRITE_NOTEBOOKS: every notebook the filter shows.
ANY_NOTEBOOK = "*"

# A Joplin item id. The tools take note and notebook ids in this shape only, so an
# id can never smuggle a path or a query into a request to Joplin.
ID_PATTERN = r"^[0-9a-fA-F]{32}$"
ID_RE = re.compile(ID_PATTERN)


@dataclass(frozen=True)
class NotebookScope:
    """The notebooks a tool may see right now; ``visible`` is None with no filter."""

    visible: frozenset[str] | None = None

    def allows(self, notebook_id: str) -> bool:
        """True if notes in the notebook with this id may be shown."""
        return self.visible is None or notebook_id in self.visible

    def allows_note(self, note: JsonDict) -> bool:
        """True if this raw Joplin note (it must carry ``parent_id``) may be shown.

        With a filter, a note whose notebook is unknown is hidden.
        """
        return self.allows(note.get("parent_id", ""))


UNFILTERED = NotebookScope()


@dataclass(frozen=True)
class WriteTargets:
    """The notebooks a note may be created in right now, by id, with their titles."""

    titles: Mapping[str, str] = field(default_factory=dict)

    def title_of(self, notebook_id: str) -> str | None:
        """The notebook's title if a note may be created in it, else None."""
        return self.titles.get(notebook_id)


class _Notebooks:
    """Joplin's flat notebook list, indexed for looking entries up and walking down."""

    def __init__(self, folders: Sequence[JsonDict]) -> None:
        self.ids = {folder["id"] for folder in folders}
        self._children: dict[str, list[str]] = {}
        self._titled: dict[str, list[str]] = {}
        for folder in folders:
            self._children.setdefault(folder.get("parent_id", ""), []).append(folder["id"])
            self._titled.setdefault(folder.get("title", ""), []).append(folder["id"])

    def find(self, variable: str, entry: str) -> str:
        """The id of the one notebook ``entry`` names, or a NotebookFilterError."""
        if ID_RE.fullmatch(entry):
            notebook_id = entry.lower()
            if notebook_id not in self.ids:
                raise NotebookFilterError(f"{variable}: no notebook has the id {entry}")
            return notebook_id
        matches = self._titled.get(entry, [])
        if not matches:
            raise NotebookFilterError(f"{variable}: no notebook is titled {entry!r}")
        if len(matches) > 1:
            raise NotebookFilterError(
                f"{variable}: {len(matches)} notebooks are titled {entry!r}; name the one "
                f"you mean by its id ({', '.join(sorted(matches))})"
            )
        return matches[0]

    def rooted(self) -> set[str]:
        """Every notebook whose chain of parents ends at a top-level notebook.

        Leaves out a notebook whose parent is missing from the list, and a loop of
        notebooks that contain each other: nobody can say what those sit under.
        """
        found: set[str] = set()
        for top in self._children.get("", []):
            found |= self.subtree(top)
        return found

    def subtree(self, root: str) -> set[str]:
        """``root`` and every notebook under it."""
        found: set[str] = set()
        pending = [root]
        while pending:
            notebook_id = pending.pop()
            if notebook_id in found:  # a cycle can't loop for ever
                continue
            found.add(notebook_id)
            pending.extend(self._children.get(notebook_id, []))
        return found


def resolve_scope(
    include: Sequence[str], exclude: Sequence[str], folders: Sequence[JsonDict]
) -> NotebookScope:
    """Turn the two lists into the set of visible notebook ids.

    ``folders`` are raw Joplin dicts with ``id``, ``title`` and ``parent_id``.
    Raises :class:`NotebookFilterError` when an entry names no notebook, names
    more than one, or is shown by one list and hidden by the other.
    """
    if not include and not exclude:
        return UNFILTERED
    notebooks = _Notebooks(folders)
    hidden: set[str] = set()
    for entry in exclude:
        hidden |= notebooks.subtree(notebooks.find(EXCLUDE_VAR, entry))
    if not include:
        # Only what provably isn't under a hidden notebook: one that can't be
        # traced to the top might be, so it stays hidden.
        return NotebookScope(frozenset(notebooks.rooted() - hidden))
    shown: set[str] = set()
    for entry in include:
        root = notebooks.find(INCLUDE_VAR, entry)
        if root in hidden:
            raise NotebookFilterError(
                f"{INCLUDE_VAR}: {entry!r} is hidden by {EXCLUDE_VAR}, so it could never "
                "be seen; drop it from one of the two"
            )
        shown |= notebooks.subtree(root)
    return NotebookScope(frozenset(shown - hidden))


def resolve_write_targets(
    write: Sequence[str], scope: NotebookScope, folders: Sequence[JsonDict]
) -> WriteTargets:
    """Turn ``SBJ_WRITE_NOTEBOOKS`` into the notebooks that may receive a note.

    Always a subset of what ``scope`` shows. Raises :class:`NotebookFilterError`
    when an entry names no notebook, names more than one, or names a hidden one
    (listing it could never make it writable, so it is a mistake to point out).
    """
    if not write:
        return WriteTargets()
    notebooks = _Notebooks(folders)
    chosen: set[str] = set()
    for entry in write:
        if entry == ANY_NOTEBOOK:
            chosen |= notebooks.ids
            continue
        root = notebooks.find(WRITE_VAR, entry)
        if not scope.allows(root):
            raise NotebookFilterError(
                f"{WRITE_VAR}: {entry!r} is hidden by the notebook filter, so no note "
                "could be created there"
            )
        chosen |= notebooks.subtree(root)
    return WriteTargets(
        {
            folder["id"]: folder.get("title", "")
            for folder in folders
            if folder["id"] in chosen and scope.allows(folder["id"])
        }
    )


def refuse_blank_filter(settings: Settings) -> None:
    """Raise if a filter variable is set but lists no notebook.

    Set to nothing, ``SBJ_NOTEBOOKS`` could mean "show none" or "no filter". The
    second reading shows everything, so neither is assumed.
    """
    if settings.blank_filter_vars:
        names = " and ".join(settings.blank_filter_vars)
        raise NotebookFilterError(
            f"{names}: set, but lists no notebook; list at least one, or remove the variable"
        )


def scope_of(settings: Settings, folders: Sequence[JsonDict]) -> NotebookScope:
    """Resolve the configured filter against notebooks already fetched."""
    refuse_blank_filter(settings)
    return resolve_scope(settings.notebooks, settings.exclude_notebooks, folders)


async def current_scope(client: JoplinClient, settings: Settings) -> NotebookScope:
    """The scope as of now. Asks Joplin for its notebooks only when a filter is set."""
    if not settings.notebook_filter_set:
        return UNFILTERED
    return scope_of(settings, await client.get_folders())


def write_targets_of(settings: Settings, folders: Sequence[JsonDict]) -> WriteTargets:
    """Resolve where notes may be created against notebooks already fetched."""
    return resolve_write_targets(settings.write_notebooks, scope_of(settings, folders), folders)


async def current_write_targets(client: JoplinClient, settings: Settings) -> WriteTargets:
    """Where a note may be created as of now. Asks Joplin only when writes are on."""
    if not settings.writes_enabled:
        return WriteTargets()
    return write_targets_of(settings, await client.get_folders())


async def check_at_startup(settings: Settings) -> None:
    """Refuse to start with notebook settings that Joplin's notebooks contradict.

    Raises :class:`NotebookFilterError` for a wrong filter or write list. When
    Joplin isn't answering there is nothing to check against, so the server
    starts anyway: every call resolves the settings again and refuses if they are
    wrong, which keeps the server's start independent of Joplin's without ever
    failing open.
    """
    refuse_blank_filter(settings)  # wrong whatever Joplin says, so it needn't be asked
    if not settings.notebook_filter_set:
        # Said out loud, so a misspelt variable name doesn't pass for a filter.
        logger.info("no notebook filter is set: every notebook is readable")
    if not (settings.notebook_filter_set or settings.writes_enabled):
        return
    client = JoplinClient(settings)
    try:
        folders = await client.get_folders()
    except JoplinError as exc:
        logger.warning(
            "the notebook settings couldn't be checked at start-up, and are checked "
            "again on every call: %s",
            exc,
        )
        return
    finally:
        await client.aclose()
    scope = scope_of(settings, folders)
    targets = write_targets_of(settings, folders)
    if scope.visible is not None:
        logger.info("notebook filter: %d of %d notebooks visible", len(scope.visible), len(folders))
    if settings.writes_enabled:
        logger.info("note creation: allowed in %d notebooks", len(targets.titles))
