"""A short memory of the notes this process asked Joplin to create.

A note is created by one request, and requests get repeated: a client that timed
out sends the call again, a model that saw an error tries once more. Without a
memory, each repeat is a second copy of the note. So the write tool remembers, for
a few minutes, which id it sent for which note (same notebook, title and text),
and looks for that note before making another.

Kept in memory only and never written anywhere: it holds digests and ids, no note
text, and it is fine to lose on a restart.
"""

import hashlib
import time
from collections import OrderedDict
from collections.abc import Callable

REMEMBER_SECONDS = 600.0
REMEMBER_AT_MOST = 256


def note_key(notebook_id: str, title: str, body: str) -> str:
    """A digest that is the same for the same note in the same notebook."""
    digest = hashlib.sha256()
    for part in (notebook_id, title, body):
        encoded = part.encode()
        digest.update(len(encoded).to_bytes(8, "big"))  # so parts can't run together
        digest.update(encoded)
    return digest.hexdigest()


class RecentNotes:
    """Which note id was sent for which note, for the last few minutes."""

    def __init__(
        self,
        seconds: float = REMEMBER_SECONDS,
        at_most: int = REMEMBER_AT_MOST,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._seconds = seconds
        self._at_most = at_most
        self._clock = clock
        self._sent: OrderedDict[str, tuple[str, float]] = OrderedDict()

    def get(self, key: str) -> str | None:
        """The id sent for this note, if it was sent recently enough."""
        entry = self._sent.get(key)
        if entry is None:
            return None
        note_id, at = entry
        if self._clock() - at > self._seconds:
            del self._sent[key]
            return None
        return note_id

    def put(self, key: str, note_id: str) -> None:
        """Remember that ``note_id`` was sent for this note, forgetting the oldest if full."""
        self._sent.pop(key, None)
        self._sent[key] = (note_id, self._clock())
        while len(self._sent) > self._at_most:
            self._sent.popitem(last=False)

    def forget(self, key: str) -> None:
        """Drop a note that turned out not to have been created."""
        self._sent.pop(key, None)
