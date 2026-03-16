"""Reader routes: main feed and article expansion."""

from typing import Any

from flask import Blueprint, redirect, render_template, session, url_for

from app.services import article_service, profile_service

reader_bp = Blueprint("reader", __name__)


@reader_bp.route("/")
def index() -> Any:
    """Main feed view. Redirect to /setup if no profile."""
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    profile = profile_service.get_profile_with_selections(user_id)
    if not profile:
        return redirect(url_for("setup.setup_page"))

    feed = article_service.get_feed(user_id)
    return render_template("index.html", feed=feed, profile=profile)


@reader_bp.route("/clusters/<cluster_id>/expand")
def expand_cluster(cluster_id: str) -> Any:
    """Return article_expanded partial for HTMX swap."""
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    profile = profile_service.get_profile_with_selections(user_id)
    if not profile:
        return redirect(url_for("setup.setup_page"))

    profile_hash = profile_service.compute_profile_hash(profile)
    cluster = article_service.get_expanded_cluster(cluster_id, profile_hash)
    if not cluster:
        return render_template(
            "partials/article_expanded.html",
            article=None,
            error="Article not found.",
        )
    return render_template("partials/article_expanded.html", article=cluster)
