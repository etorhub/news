"""Settings page: edit profile after initial setup."""

from typing import Any

from flask import Blueprint, redirect, render_template, request, session, url_for

from app.config import load_sources
from app.db import rewrite_requests as db_rewrite_requests
from app.services import profile_service

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")

REWRITE_TONE_OPTIONS = [
    ("Short sentences. Simple vocabulary. No jargon.", "Simple (default)"),
    (
        "Very short sentences. One idea per sentence. Elementary vocabulary.",
        "Very simple",
    ),
    (
        "Short sentences. Calm, reassuring tone. Avoid alarming phrasing.",
        "Calm",
    ),
    ("Short sentences. Formal but clear. Avoid colloquialisms.", "Formal"),
]


def _all_topics(sources: list[dict[str, Any]]) -> list[str]:
    """Collect unique topic ids from sources."""
    seen: set[str] = set()
    result: list[str] = []
    for s in sources:
        for t in s.get("topics", []):
            if t not in seen:
                seen.add(t)
                result.append(t)
    return sorted(result)


@settings_bp.route("/", methods=["GET", "POST"])
def settings_page() -> Any:
    """GET: show settings form with current values. POST: update and redirect back."""
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    profile = profile_service.get_profile_with_selections(user_id)
    if not profile:
        return redirect(url_for("setup.setup_page"))

    sources = load_sources()
    topics = _all_topics(sources)

    if request.method == "GET":
        return render_template(
            "settings.html",
            profile=profile,
            sources=sources,
            topics=topics,
            rewrite_tone_options=REWRITE_TONE_OPTIONS,
            needs_regeneration_confirmation=False,
        )

    location = request.form.get("location", "").strip() or None
    language = request.form.get("language", "ca").strip()
    filter_negative = request.form.get("filter_negative") == "on"
    rewrite_tone = request.form.get(
        "rewrite_tone",
        "Short sentences. Simple vocabulary. No jargon.",
    ).strip()
    high_contrast = request.form.get("high_contrast") == "on"

    source_ids = request.form.getlist("sources")
    if not source_ids:
        source_ids = [s["id"] for s in sources]
    topic_ids = request.form.getlist("topics")
    if not topic_ids:
        topic_ids = topics

    form_data = {
        "location": location,
        "language": language,
        "filter_negative": filter_negative,
        "rewrite_tone": rewrite_tone,
        "high_contrast": high_contrast,
    }

    confirm_regenerate = request.form.get("confirm_regenerate") == "1"
    needs_regeneration = profile_service.regeneration_needed(
        profile, form_data, source_ids, topic_ids
    )

    if needs_regeneration and not confirm_regenerate:
        display_profile = {
            **profile,
            "location": form_data.get("location"),
            "language": form_data.get("language"),
            "filter_negative": form_data.get("filter_negative"),
            "rewrite_tone": form_data.get("rewrite_tone"),
            "high_contrast": form_data.get("high_contrast"),
            "source_ids": source_ids,
            "topic_ids": topic_ids,
        }
        return render_template(
            "settings.html",
            profile=display_profile,
            sources=sources,
            topics=topics,
            rewrite_tone_options=REWRITE_TONE_OPTIONS,
            needs_regeneration_confirmation=True,
        )

    profile_service.save_setup(user_id, form_data, source_ids, topic_ids)

    if needs_regeneration:
        db_rewrite_requests.enqueue_rewrite(user_id)

    return redirect(url_for("settings.settings_page") + "?saved=1")
