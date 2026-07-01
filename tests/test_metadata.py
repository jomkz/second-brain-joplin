"""Guard that packaging metadata stays wired to the single version source."""

from importlib.metadata import version

from second_brain_joplin import __version__


def test_installed_version_matches_dunder():
    assert version("second-brain-joplin") == __version__
