"""Pure diffing between Joplin's current notes and the indexed versions."""

from .types import SyncPlan


def diff_versions(current: dict[str, str], indexed: dict[str, str]) -> SyncPlan:
    """Compute which notes need re-embedding and which to drop.

    ``current`` maps note id → version marker (Joplin ``updated_time``) for every
    live note; ``indexed`` is the same map for what the vector store already holds.
    A note is *changed* when it is new or its marker differs; *deleted* when it is
    in the index but no longer live.
    """
    changed_ids = [
        note_id for note_id, version in current.items() if indexed.get(note_id) != version
    ]
    deleted_ids = [note_id for note_id in indexed if note_id not in current]
    return SyncPlan(changed_ids=changed_ids, deleted_ids=deleted_ids)
