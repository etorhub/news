"""User profile and setup wizard logic."""

import hashlib
import json
from typing import Any

from app.db import users

REGENERATION_FIELDS = (
    "location",
    "language",
    "rewrite_tone",
    "filter_negative",
    "source_ids",
    "topic_ids",
)


def regeneration_needed(
    old_profile: dict[str, Any],
    new_form_data: dict[str, Any],
    new_source_ids: list[str],
    new_topic_ids: list[str],
) -> bool:
    """Return True if any regeneration-affecting field changed."""
    old_sources = set(old_profile.get("source_ids", []))
    old_topics = set(old_profile.get("topic_ids", []))
    new_sources = set(new_source_ids)
    new_topics = set(new_topic_ids)
    if old_sources != new_sources or old_topics != new_topics:
        return True
    if (old_profile.get("location") or None) != (new_form_data.get("location") or None):
        return True
    if old_profile.get("language", "ca") != new_form_data.get("language", "ca"):
        return True
    default_tone = "Short sentences. Simple vocabulary. No jargon."
    if old_profile.get("rewrite_tone", default_tone) != new_form_data.get(
        "rewrite_tone", default_tone
    ):
        return True
    return old_profile.get("filter_negative", False) != new_form_data.get(
        "filter_negative", False
    )


def compute_profile_hash(profile: dict[str, Any]) -> str:
    """Compute cache key for rewrites. Includes only rewrite-affecting fields."""
    language = (profile.get("language") or "ca").strip() or "ca"
    fields = {
        "language": language,
        "rewrite_tone": profile.get(
            "rewrite_tone", "Short sentences. Simple vocabulary. No jargon."
        ),
        "filter_negative": profile.get("filter_negative", False),
    }
    return hashlib.sha256(
        json.dumps(fields, sort_keys=True).encode()
    ).hexdigest()


def save_setup(
    user_id: int,
    form_data: dict[str, Any],
    source_ids: list[str],
    topic_ids: list[str],
) -> None:
    """Create or update profile and save source/topic selections."""
    profile_data = {
        "location": form_data.get("location"),
        "language": form_data.get("language", "ca"),
        "filter_negative": form_data.get("filter_negative", False),
        "rewrite_tone": form_data.get(
            "rewrite_tone", "Short sentences. Simple vocabulary. No jargon."
        ),
        "high_contrast": form_data.get("high_contrast", False),
    }
    existing = users.get_profile(user_id)
    if existing:
        users.update_profile(user_id, profile_data)
    else:
        users.create_profile(user_id, profile_data)
    users.set_user_sources(user_id, source_ids)
    users.set_user_topics(user_id, topic_ids)


def get_profile_with_selections(user_id: int) -> dict[str, Any]:
    """Return profile dict with source_ids and topic_ids lists."""
    profile = users.get_profile(user_id)
    if not profile:
        return {}
    return {
        **profile,
        "source_ids": users.get_user_sources(user_id),
        "topic_ids": users.get_user_topics(user_id),
    }
