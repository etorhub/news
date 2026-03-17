"""Dashboard overview view."""

from flask import Blueprint, Response, render_template

from app.config import load_config
from app.db import admin as admin_db

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
def index() -> Response:
    """Overview dashboard with stats and incidents."""
    config = load_config()
    stats = admin_db.get_overview_stats()
    feed_health = admin_db.get_feed_health()
    pipeline_stats = admin_db.get_article_pipeline_stats()
    clustering_stats = admin_db.get_clustering_stats()
    rewrite_failures = admin_db.get_recent_rewrite_failures(hours=24, limit=20)
    incidents = admin_db.get_incidents(config)
    job_runs = admin_db.get_recent_job_runs(limit=10)

    return render_template(
        "ops/dashboard.html",
        stats=stats,
        feed_health=feed_health,
        pipeline_stats=pipeline_stats,
        clustering_stats=clustering_stats,
        rewrite_failures=rewrite_failures,
        incidents=incidents,
        job_runs=job_runs,
    )
