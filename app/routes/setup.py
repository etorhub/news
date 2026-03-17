"""Setup wizard: initial configuration after registration."""

from typing import Any

from flask import Blueprint, redirect, render_template, request, session, url_for

from app.config import load_sources
from app.db import rewrite_requests as db_rewrite_requests
from app.services import profile_service

setup_bp = Blueprint("setup", __name__, url_prefix="/setup")

REWRITE_TONE_OPTIONS = [
    (
        "Journalistic style. Formal and well-written. Do not simplify; preserve original complexity and nuance. Avoid spoilers in headlines or summaries.",
        "Neutral (default)",
    ),
    ("Short sentences. Simple vocabulary. No jargon.", "Simple"),
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


@setup_bp.route("/", methods=["GET", "POST"])
def setup_page() -> Any:
    """GET: show setup form. POST: save and redirect to /."""
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    sources = load_sources()
    topics = _all_topics(sources)

    if request.method == "GET":
        return render_template(
            "setup.html",
            sources=sources,
            topics=topics,
            rewrite_tone_options=REWRITE_TONE_OPTIONS,
        )

    location = request.form.get("location", "").strip() or None
    language = request.form.get("language", "ca").strip()
    filter_negative = request.form.get("filter_negative") == "on"
    rewrite_tone = request.form.get(
        "rewrite_tone",
        "Journalistic style. Formal and well-written. Do not simplify; preserve original complexity and nuance. Avoid spoilers in headlines or summaries.",
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
    profile_service.save_setup(user_id, form_data, source_ids, topic_ids)

    db_rewrite_requests.enqueue_rewrite(user_id)

    return redirect(url_for("reader.index"))
