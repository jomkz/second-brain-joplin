"""Tests for the version-diff sync planner."""

from second_brain_joplin.semantic.sync import diff_versions


def test_new_note_is_changed() -> None:
    plan = diff_versions({"a": "1"}, {})
    assert plan.changed_ids == ["a"]
    assert plan.deleted_ids == []


def test_updated_time_change_is_changed() -> None:
    plan = diff_versions({"a": "2"}, {"a": "1"})
    assert plan.changed_ids == ["a"]
    assert plan.deleted_ids == []


def test_unchanged_note_is_skipped() -> None:
    plan = diff_versions({"a": "1"}, {"a": "1"})
    assert plan.changed_ids == []
    assert plan.deleted_ids == []


def test_missing_note_is_deleted() -> None:
    plan = diff_versions({}, {"a": "1"})
    assert plan.changed_ids == []
    assert plan.deleted_ids == ["a"]


def test_mixed_add_change_delete() -> None:
    current = {"keep": "1", "changed": "2", "new": "1"}
    indexed = {"keep": "1", "changed": "1", "gone": "1"}
    plan = diff_versions(current, indexed)
    assert sorted(plan.changed_ids) == ["changed", "new"]
    assert plan.deleted_ids == ["gone"]


def test_empty_inputs() -> None:
    plan = diff_versions({}, {})
    assert plan.changed_ids == []
    assert plan.deleted_ids == []
