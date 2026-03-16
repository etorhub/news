"""Settings page: edit profile after initial setup."""

import threading
from typing import Any

from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.config import load_sources
from app.services import profile_service, rewrite_service

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
    profile_service.save_setup(user_id, form_data, source_ids, topic_ids)

    def _run_rewrite_with_app(app: Any, uid: int) -> None:
        with app.app_context():
            rewrite_service.run_rewrite_for_user(uid)

    app = current_app._get_current_object()
    threading.Thread(
        target=lambda: _run_rewrite_with_app(app, user_id),
        daemon=True,
    ).start()

    return redirect(url_for("settings.settings_page") + "?saved=1")
