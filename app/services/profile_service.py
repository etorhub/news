"""User profile and setup wizard logic."""

import hashlib
import json
from typing import Any

from app.db import users


def compute_profile_hash(profile: dict[str, Any]) -> str:
    """Compute cache key for rewrites. Includes only rewrite-affecting fields."""
    fields = {
        "language": profile.get("language", "ca"),
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
