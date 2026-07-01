"""Split a note into overlapping text chunks for embedding.

Pure and deterministic: paragraph-aware packing into fixed-size character
windows with a small overlap, each chunk prefixed with the note title so the
embedding carries a bit of context.
"""

import re

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 100

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")


def chunk_note(
    title: str,
    body: str,
    *,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """Return title-prefixed chunks of ``body``; empty/whitespace body → ``[]``."""
    text = body.strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT.split(text) if p.strip()]

    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if not current:
            current = para
        elif len(current) + 2 + len(para) <= chunk_size:
            current = f"{current}\n\n{para}"
        else:
            chunks.append(current)
            current = para
        while len(current) > chunk_size:
            chunks.append(current[:chunk_size])
            current = current[chunk_size - overlap :]
    # `current` is always non-empty here: text was non-empty, so there is at least
    # one paragraph, and each window split leaves a non-empty remainder.
    chunks.append(current)

    prefix = f"{title.strip()}\n\n" if title.strip() else ""
    return [f"{prefix}{chunk}" for chunk in chunks]
