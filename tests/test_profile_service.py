"""Tests for profile_service."""

from app.services.profile_service import regeneration_needed


def test_regeneration_needed_when_language_changes() -> None:
    """regeneration_needed returns True when language changes."""
    old = {"language": "ca", "source_ids": ["s1"], "topic_ids": ["t1"]}
    new_form = {"language": "es", "filter_negative": False}
    assert regeneration_needed(old, new_form, ["s1"], ["t1"]) is True


def test_regeneration_needed_when_source_ids_change() -> None:
    """regeneration_needed returns True when source_ids change."""
    old = {"language": "ca", "source_ids": ["s1"], "topic_ids": ["t1"]}
    new_form = {"language": "ca", "filter_negative": False}
    assert regeneration_needed(old, new_form, ["s1", "s2"], ["t1"]) is True


def test_regeneration_needed_when_topic_ids_change() -> None:
    """regeneration_needed returns True when topic_ids change."""
    old = {"language": "ca", "source_ids": ["s1"], "topic_ids": ["t1"]}
    new_form = {"language": "ca", "filter_negative": False}
    assert regeneration_needed(old, new_form, ["s1"], ["t1", "t2"]) is True


def test_regeneration_needed_when_rewrite_tone_changes() -> None:
    """regeneration_needed returns True when rewrite_tone changes."""
    old = {
        "language": "ca",
        "rewrite_tone": "Short sentences.",
        "source_ids": ["s1"],
        "topic_ids": ["t1"],
    }
    new_form = {
        "language": "ca",
        "rewrite_tone": "Very short sentences.",
        "filter_negative": False,
    }
    assert regeneration_needed(old, new_form, ["s1"], ["t1"]) is True


def test_regeneration_needed_when_filter_negative_changes() -> None:
    """regeneration_needed returns True when filter_negative changes."""
    old = {
        "language": "ca",
        "filter_negative": False,
        "source_ids": ["s1"],
        "topic_ids": ["t1"],
    }
    new_form = {"language": "ca", "filter_negative": True}
    assert regeneration_needed(old, new_form, ["s1"], ["t1"]) is True


def test_regeneration_needed_when_location_changes() -> None:
    """regeneration_needed returns True when location changes."""
    old = {
        "location": "Barcelona",
        "language": "ca",
        "source_ids": ["s1"],
        "topic_ids": ["t1"],
    }
    new_form = {"location": "Madrid", "language": "ca", "filter_negative": False}
    assert regeneration_needed(old, new_form, ["s1"], ["t1"]) is True


def test_regeneration_not_needed_when_only_high_contrast_changes() -> None:
    """regeneration_needed returns False when only high_contrast changes."""
    old = {
        "language": "ca",
        "rewrite_tone": "Short sentences.",
        "filter_negative": False,
        "source_ids": ["s1"],
        "topic_ids": ["t1"],
    }
    new_form = {
        "language": "ca",
        "rewrite_tone": "Short sentences.",
        "filter_negative": False,
        "high_contrast": True,
    }
    assert regeneration_needed(old, new_form, ["s1"], ["t1"]) is False


def test_regeneration_not_needed_when_nothing_changes() -> None:
    """regeneration_needed returns False when no regeneration field changes."""
    old = {"language": "ca", "source_ids": ["s1"], "topic_ids": ["t1"]}
    new_form = {"language": "ca", "filter_negative": False}
    assert regeneration_needed(old, new_form, ["s1"], ["t1"]) is False


def test_regeneration_not_needed_when_source_order_differs() -> None:
    """regeneration_needed returns False when source_ids same but order differs."""
    old = {"language": "ca", "source_ids": ["s1", "s2"], "topic_ids": ["t1"]}
    new_form = {"language": "ca", "filter_negative": False}
    assert regeneration_needed(old, new_form, ["s2", "s1"], ["t1"]) is False
