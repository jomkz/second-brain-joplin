"""Tests for the short memory of notes the write tool sent (recent.py)."""

from second_brain_joplin.recent import RecentNotes, note_key


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_the_same_note_in_the_same_notebook_has_the_same_key() -> None:
    assert note_key("nb", "Title", "body") == note_key("nb", "Title", "body")


def test_any_difference_makes_another_key() -> None:
    base = note_key("nb", "Title", "body")
    assert note_key("other", "Title", "body") != base
    assert note_key("nb", "Title!", "body") != base
    assert note_key("nb", "Title", "body ") != base


def test_text_cannot_slide_between_the_title_and_the_body() -> None:
    assert note_key("nb", "ab", "c") != note_key("nb", "a", "bc")
    assert note_key("nb", "a", "") != note_key("nb", "", "a")
    assert note_key("n", "ba", "c") != note_key("nb", "a", "c")


def test_the_key_holds_no_note_text() -> None:
    key = note_key("nb", "A secret title", "a secret body")
    assert "secret" not in key and len(key) == 64


def test_a_sent_note_is_remembered() -> None:
    recent = RecentNotes()
    assert recent.get("k") is None
    recent.put("k", "id-1")
    assert recent.get("k") == "id-1"


def test_it_forgets_after_the_window() -> None:
    clock = Clock()
    recent = RecentNotes(seconds=600, clock=clock)
    recent.put("k", "id-1")
    clock.now += 600
    assert recent.get("k") == "id-1"  # still inside
    clock.now += 1
    assert recent.get("k") is None
    assert recent.get("k") is None  # and stays forgotten


def test_sending_again_restarts_the_window_and_replaces_the_id() -> None:
    clock = Clock()
    recent = RecentNotes(seconds=600, clock=clock)
    recent.put("k", "id-1")
    clock.now += 500
    recent.put("k", "id-2")
    clock.now += 500
    assert recent.get("k") == "id-2"


def test_forget_drops_a_note_that_was_not_created() -> None:
    recent = RecentNotes()
    recent.put("k", "id-1")
    recent.forget("k")
    recent.forget("never there")  # no error
    assert recent.get("k") is None


def test_it_holds_a_bounded_number_and_drops_the_oldest() -> None:
    recent = RecentNotes(at_most=3)
    for n in range(5):
        recent.put(f"k{n}", f"id-{n}")
    assert [recent.get(f"k{n}") for n in range(5)] == [None, None, "id-2", "id-3", "id-4"]
