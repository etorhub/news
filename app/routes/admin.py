"""Admin dashboard routes. Requires is_admin."""

from typing import Any

from flask import Blueprint, abort, render_template, request, session

from app.config import load_config
from app.db import admin as admin_db
from app.db import sources as db_sources
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


def _articles_page_params() -> dict[str, Any]:
    """Parse common query params for articles page."""
    view = request.args.get("view", "articles")
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(10, request.args.get("per_page", 50, type=int)))
    extraction_status = request.args.get("extraction_status") or None
    source_id = request.args.get("source_id") or None
    return {
        "view": view,
        "page": page,
        "per_page": per_page,
        "extraction_status": extraction_status,
        "source_id": source_id,
    }


@admin_bp.route("/articles")
def articles_page() -> Any:
    """Articles and clusters browse page."""
    params = _articles_page_params()
    sources = db_sources.get_all_sources()

    if params["view"] == "clusters":
        total = admin_db.get_admin_clusters_count()
        offset = (params["page"] - 1) * params["per_page"]
        clusters = admin_db.get_admin_clusters(
            limit=params["per_page"],
            offset=offset,
        )
        return render_template(
            "admin/articles.html",
            clusters=clusters,
            total=total,
            sources=sources,
            **params,
        )

    total = admin_db.get_admin_articles_count(
        extraction_status=params["extraction_status"],
        source_id=params["source_id"],
    )
    offset = (params["page"] - 1) * params["per_page"]
    articles = admin_db.get_admin_articles(
        limit=params["per_page"],
        offset=offset,
        extraction_status=params["extraction_status"],
        source_id=params["source_id"],
    )
    return render_template(
        "admin/articles.html",
        articles=articles,
        total=total,
        sources=sources,
        **params,
    )


@admin_bp.route("/articles/partials/articles")
def articles_partial() -> Any:
    """HTMX partial: paginated articles table."""
    params = _articles_page_params()
    total = admin_db.get_admin_articles_count(
        extraction_status=params["extraction_status"],
        source_id=params["source_id"],
    )
    offset = (params["page"] - 1) * params["per_page"]
    articles = admin_db.get_admin_articles(
        limit=params["per_page"],
        offset=offset,
        extraction_status=params["extraction_status"],
        source_id=params["source_id"],
    )
    return render_template(
        "admin/partials/articles_table.html",
        articles=articles,
        total=total,
        **params,
    )


@admin_bp.route("/articles/partials/clusters")
def clusters_partial() -> Any:
    """HTMX partial: paginated clusters list."""
    params = _articles_page_params()
    total = admin_db.get_admin_clusters_count()
    offset = (params["page"] - 1) * params["per_page"]
    clusters = admin_db.get_admin_clusters(
        limit=params["per_page"],
        offset=offset,
    )
    return render_template(
        "admin/partials/clusters_list.html",
        clusters=clusters,
        total=total,
        **params,
    )


@admin_bp.route("/articles/partials/cluster_detail")
def cluster_detail_partial() -> Any:
    """HTMX partial: single cluster's articles."""
    cluster_id = request.args.get("cluster_id")
    if not cluster_id:
        return render_template("admin/partials/cluster_detail.html", articles=[])
    articles = admin_db.get_admin_cluster_articles(cluster_id)
    return render_template(
        "admin/partials/cluster_detail.html",
        cluster_id=cluster_id,
        articles=articles,
    )
