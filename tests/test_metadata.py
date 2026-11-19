"""Guard that packaging metadata stays wired to the single version source."""

from importlib.metadata import metadata, version

from second_brain_joplin import __version__


def test_installed_version_matches_dunder() -> None:
    assert version("second-brain-joplin") == __version__


def test_license_metadata_names_the_agpl_and_nothing_else() -> None:
    """One license statement, as an SPDX expression.

    A leftover ``License ::`` classifier would be a second statement of the
    license beside the expression, and the old one named MIT.
    """
    meta = metadata("second-brain-joplin")
    assert meta["License-Expression"] == "AGPL-3.0-or-later"
    assert [c for c in meta.get_all("Classifier") or [] if c.startswith("License ::")] == []
