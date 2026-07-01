"""Semantic search: embedding index over Joplin notes.

This subpackage is import-light: nothing here pulls in the optional ML/vector
dependencies at import time. The concrete backends live in :mod:`.backends`,
which is imported lazily (only when a semantic tool is actually invoked) so the
base install and the packaged-wheel smoke test never require the extras.
"""
