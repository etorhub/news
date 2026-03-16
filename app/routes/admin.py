"""Admin dashboard routes. Requires is_admin."""

from typing import Any

from flask import Blueprint, abort, render_template, session

from app.config import load_config
from app.db import admin as admin_db
from app.db import users as db_users

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.before_request
def require_admin() -> None:
    """Ensure the current user is an admin. Returns 403 if not."""
    user_id = session.get("user_id")
    if not user_id:
        return
    user = db_users.get_user_by_id(user_id)
    if not user or not user.get("is_admin"):
        abort(403)


@admin_bp.route("/")
def dashboard() -> Any:
    """Full admin dashboard page."""
    config = load_config()
    stats = admin_db.get_overview_stats()
    feed_health = admin_db.get_feed_health()
    pipeline_stats = admin_db.get_article_pipeline_stats()
    clustering_stats = admin_db.get_clustering_stats()
    rewrite_failures = admin_db.get_recent_rewrite_failures(hours=24, limit=50)
    users_list = admin_db.get_admin_users()
    incidents = admin_db.get_incidents(config)
    job_runs = admin_db.get_recent_job_runs(limit=20)

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        feed_health=feed_health,
        pipeline_stats=pipeline_stats,
        clustering_stats=clustering_stats,
        rewrite_failures=rewrite_failures,
        users_list=users_list,
        incidents=incidents,
        job_runs=job_runs,
    )


@admin_bp.route("/partials/jobs")
def jobs_partial() -> Any:
    """HTMX partial: recent job runs. Auto-refreshed every 60s."""
    job_runs = admin_db.get_recent_job_runs(limit=20)
    return render_template("admin/partials/jobs.html", job_runs=job_runs)
