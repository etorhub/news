"""Stories (clusters) view."""

from flask import Blueprint, Response, render_template, request

from app.config import load_config
from app.db import admin as admin_db

stories_bp = Blueprint("stories", __name__)


@stories_bp.route("/")
def index() -> Response:
    """Stories list with rewrite status matrix."""
    config = load_config()
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(10, request.args.get("per_page", 50, type=int)))

    total = admin_db.get_admin_stories_count()
    offset = (page - 1) * per_page
    stories = admin_db.get_stories_with_rewrite_status(
        limit=per_page,
        offset=offset,
        config=config,
    )

    return render_template(
        "ops/stories.html",
        stories=stories,
        total=total,
        page=page,
        per_page=per_page,
    )


@stories_bp.route("/partials/detail/<story_id>")
def story_detail_partial(story_id: str) -> Response:
    """HTMX partial: story articles and rewrite details."""
    articles = admin_db.get_admin_story_articles(story_id)
    return render_template(
        "ops/partials/story_detail.html",
        story_id=story_id,
        articles=articles,
    )
