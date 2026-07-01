"""Tests for note chunking."""

import pytest

from second_brain_joplin.semantic.chunking import chunk_note


@pytest.mark.parametrize("body", ["", "   ", "\n\n  \n"])
def test_empty_body_yields_no_chunks(body: str) -> None:
    assert chunk_note("Title", body) == []


def test_short_body_is_a_single_titled_chunk() -> None:
    chunks = chunk_note("My Note", "A short body.")
    assert chunks == ["My Note\n\nA short body."]


def test_boundary_length_body_stays_single_chunk() -> None:
    body = "x" * 1000
    chunks = chunk_note("", body, chunk_size=1000, overlap=100)
    assert len(chunks) == 1
    assert chunks[0] == body


def test_long_body_splits_with_overlap() -> None:
    # distinct characters so the overlap assertion checks real offsets
    body = "".join(chr(33 + (i % 90)) for i in range(2500))
    chunks = chunk_note("", body, chunk_size=1000, overlap=100)
    assert len(chunks) == 3
    assert chunks == [body[0:1000], body[900:1900], body[1800:2500]]
    # consecutive chunks share `overlap` trailing/leading characters
    assert chunks[1].startswith(chunks[0][-100:])
    assert chunks[2].startswith(chunks[1][-100:])


def test_paragraphs_pack_until_the_window_fills() -> None:
    body = "para one\n\npara two\n\npara three"
    chunks = chunk_note("", body, chunk_size=1000, overlap=100)
    assert chunks == ["para one\n\npara two\n\npara three"]


def test_paragraphs_flush_when_next_would_overflow() -> None:
    body = "a" * 600 + "\n\n" + "b" * 600
    chunks = chunk_note("", body, chunk_size=1000, overlap=100)
    assert chunks == ["a" * 600, "b" * 600]


def test_title_is_prefixed_and_whitespace_normalized() -> None:
    chunks = chunk_note("  Spaced Title  ", "  body text  ")
    assert chunks == ["Spaced Title\n\nbody text"]
