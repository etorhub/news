"""Reader routes: main feed and article expansion."""

from typing import Any

from flask import Blueprint, redirect, render_template, request, session, url_for

from app.config import load_config
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

    feed, rewrites_pending = article_service.get_feed(user_id)
    return render_template("index.html", feed=feed, rewrites_pending=rewrites_pending, profile=profile)


@reader_bp.route("/feed")
def feed_partial() -> Any:
    """HTMX partial: feed content. Polled when rewrites are pending."""
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    profile = profile_service.get_profile_with_selections(user_id)
    if not profile:
        return redirect(url_for("setup.setup_page"))

    feed, rewrites_pending = article_service.get_feed(user_id)
    return render_template(
        "partials/feed_content.html",
        feed=feed,
        rewrites_pending=rewrites_pending,
    )



@reader_bp.route("/clusters/<cluster_id>/expand")
def expand_cluster(cluster_id: str) -> Any:
    """Return article_expanded partial for HTMX swap."""
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    profile = profile_service.get_profile_with_selections(user_id)
    if not profile:
        return redirect(url_for("setup.setup_page"))

    config = load_config()
    style, language = profile_service.get_reading_variant(profile, config)
    cluster = article_service.get_expanded_cluster(cluster_id, style, language, config)
    archive = request.args.get("archive") == "1"
    if not cluster:
        return render_template(
            "partials/article_expanded.html",
            article=None,
            error="Article not found.",
            archive=archive,
        )
    return render_template(
        "partials/article_expanded.html",
        article=cluster,
        archive=archive,
    )


@reader_bp.route("/clusters/<cluster_id>/collapse")
def collapse_cluster(cluster_id: str) -> Any:
    """Return article_card partial for HTMX swap (collapse expanded view)."""
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    profile = profile_service.get_profile_with_selections(user_id)
    if not profile:
        return redirect(url_for("setup.setup_page"))

    config = load_config()
    style, language = profile_service.get_reading_variant(profile, config)
    cluster = article_service.get_expanded_cluster(cluster_id, style, language, config)
    archive = request.args.get("archive") == "1"
    if not cluster:
        return render_template(
            "partials/article_expanded.html",
            article=None,
            error="Article not found.",
            archive=archive,
        )
    return render_template(
        "partials/article_card.html",
        article=cluster,
        archive=archive,
    )


@reader_bp.route("/article/<cluster_id>")
def article_page(cluster_id: str) -> Any:
    """Full-page article view."""
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    profile = profile_service.get_profile_with_selections(user_id)
    if not profile:
        return redirect(url_for("setup.setup_page"))

    config = load_config()
    style, language = profile_service.get_reading_variant(profile, config)
    cluster = article_service.get_expanded_cluster(cluster_id, style, language, config)
    if not cluster:
        return render_template("article.html", article=None, error="Article not found.")
    return render_template("article.html", article=cluster)


