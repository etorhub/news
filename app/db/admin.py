"""Admin dashboard queries: job runs, overview stats, feed health, incidents."""

from datetime import datetime
from typing import Any

import psycopg2.extras

from app.db.connection import get_connection, return_connection


def insert_job_run(job_name: str) -> int:
    """Insert a job run row. Returns the new id."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO job_runs (job_name, status)
                VALUES (%s, 'running')
                RETURNING id
                """,
                (job_name,),
            )
            row = cur.fetchone()
            assert row is not None
            job_id: int = row[0]
        conn.commit()
        return job_id
    finally:
        return_connection(conn)


def update_job_run(
    job_id: int,
    *,
    status: str = "success",
    result: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> None:
    """Update a job run with completion data."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE job_runs
                SET finished_at = NOW(),
                    duration_ms = EXTRACT(EPOCH FROM (NOW() - started_at)) * 1000,
                    status = %s,
                    result = %s,
                    error_message = %s
                WHERE id = %s
                """,
                (status, psycopg2.extras.Json(result) if result else None, error_message, job_id),
            )
        conn.commit()
    finally:
        return_connection(conn)


def get_recent_job_runs(limit: int = 20, job_name: str | None = None) -> list[dict[str, Any]]:
    """Return recent job runs, optionally filtered by job_name."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if job_name:
                cur.execute(
                    """
                    SELECT id, job_name, started_at, finished_at, duration_ms,
                           status, result, error_message
                    FROM job_runs
                    WHERE job_name = %s
                    ORDER BY started_at DESC
                    LIMIT %s
                    """,
                    (job_name, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT id, job_name, started_at, finished_at, duration_ms,
                           status, result, error_message
                    FROM job_runs
                    ORDER BY started_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
            return [dict(row) for row in cur.fetchall()]
    finally:
        return_connection(conn)


def get_last_job_run() -> dict[str, Any] | None:
    """Return the most recent job run across all jobs."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, job_name, started_at, finished_at, duration_ms,
                       status, result, error_message
                FROM job_runs
                ORDER BY started_at DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        return_connection(conn)


def get_overview_stats() -> dict[str, Any]:
    """Return overview counts for the dashboard."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM users) AS total_users,
                    (SELECT COUNT(*) FROM users WHERE is_active = true) AS active_users,
                    (SELECT COUNT(*) FROM articles WHERE fetched_at::date = CURRENT_DATE) AS articles_today,
                    (SELECT COUNT(*) FROM source_feeds WHERE feed_active = true) AS active_feeds,
                    (SELECT COUNT(*) FROM source_feeds) AS total_feeds
                """
            )
            row = cur.fetchone()
            stats = dict(row) if row else {}
            last_run = get_last_job_run()
            stats["last_job_run"] = last_run
            return stats
    finally:
        return_connection(conn)


def get_feed_health() -> list[dict[str, Any]]:
    """Return all feeds with source info for the feed health panel."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT sf.id, sf.source_id, sf.feed_url, sf.feed_label,
                       sf.feed_active, sf.consecutive_failures,
                       sf.last_fetched_at, sf.avg_articles_per_day,
                       ns.name AS source_name
                FROM source_feeds sf
                JOIN news_sources ns ON ns.id = sf.source_id
                ORDER BY sf.feed_active DESC, sf.consecutive_failures DESC,
                         sf.last_fetched_at DESC NULLS LAST
                """
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        return_connection(conn)


def get_article_pipeline_stats() -> dict[str, Any]:
    """Return extraction status breakdown and 7-day ingestion."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT extraction_status, COUNT(*) AS cnt
                FROM articles
                GROUP BY extraction_status
                """
            )
            by_status = {row["extraction_status"]: row["cnt"] for row in cur.fetchall()}

            cur.execute(
                """
                SELECT fetched_at::date AS day, COUNT(*) AS cnt
                FROM articles
                WHERE fetched_at >= CURRENT_DATE - INTERVAL '7 days'
                GROUP BY fetched_at::date
                ORDER BY day DESC
                """
            )
            by_day = [dict(row) for row in cur.fetchall()]

            return {"by_status": by_status, "by_day": by_day}
    finally:
        return_connection(conn)


def get_clustering_stats() -> dict[str, Any]:
    """Return clustering and rewrite coverage stats."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM clusters")
            total_clusters = cur.fetchone()["cnt"]

            cur.execute(
                """
                SELECT COUNT(DISTINCT article_id) AS cnt
                FROM cluster_articles
                """
            )
            articles_in_clusters = cur.fetchone()["cnt"]

            cur.execute("SELECT COUNT(*) AS cnt FROM articles WHERE embedding IS NOT NULL")
            articles_with_embedding = cur.fetchone()["cnt"]

            cur.execute(
                """
                SELECT COUNT(DISTINCT cluster_id) AS cnt
                FROM cluster_rewrites
                WHERE rewrite_failed = false
                """
            )
            clusters_with_rewrite = cur.fetchone()["cnt"]

            cur.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM cluster_rewrites
                WHERE rewrite_failed = false
                """
            )
            rewrite_variants_ok = cur.fetchone()["cnt"]

            cur.execute(
                """
                SELECT style, language, COUNT(*) AS cnt
                FROM cluster_rewrites
                WHERE rewrite_failed = false
                GROUP BY style, language
                ORDER BY style, language
                """
            )
            rewrite_coverage_by_variant = [
                {"style": row["style"], "language": row["language"], "count": row["cnt"]}
                for row in cur.fetchall()
            ]

            cur.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM cluster_rewrites
                WHERE rewrite_failed = true
                  AND created_at >= NOW() - INTERVAL '24 hours'
                """
            )
            rewrite_failures_24h = cur.fetchone()["cnt"]

            return {
                "total_clusters": total_clusters,
                "articles_in_clusters": articles_in_clusters,
                "articles_with_embedding": articles_with_embedding,
                "clusters_with_rewrite": clusters_with_rewrite,
                "rewrite_variants_ok": rewrite_variants_ok,
                "rewrite_coverage_by_variant": rewrite_coverage_by_variant,
                "rewrite_failures_24h": rewrite_failures_24h,
            }
    finally:
        return_connection(conn)


def get_recent_rewrite_failures(hours: int = 24, limit: int = 50) -> list[dict[str, Any]]:
    """Return recent cluster rewrite failures with cluster_id, style, language, created_at, error_message."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT cluster_id::text, style, language, created_at, error_message
                FROM cluster_rewrites
                WHERE rewrite_failed = true
                  AND created_at >= NOW() - INTERVAL '1 hour' * %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (hours, limit),
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        return_connection(conn)


def get_admin_users() -> list[dict[str, Any]]:
    """Return all users with profile info for the users panel."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT u.id, u.email, u.is_active, u.is_admin, u.created_at, u.last_login_at,
                       up.language
                FROM users u
                LEFT JOIN user_profiles up ON up.user_id = u.id
                ORDER BY u.created_at DESC
                """
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        return_connection(conn)


def get_incidents(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Return auto-detected incidents for the incidents panel."""
    threshold = (
        config.get("schedule", {})
        .get("fetcher", {})
        .get("circuit_breaker_threshold", 5)
    )
    incidents: list[dict[str, Any]] = []

    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Feeds deactivated by circuit breaker
            cur.execute(
                """
                SELECT sf.id, sf.source_id, sf.feed_url, sf.consecutive_failures,
                       ns.name AS source_name
                FROM source_feeds sf
                JOIN news_sources ns ON ns.id = sf.source_id
                WHERE sf.feed_active = false AND sf.consecutive_failures >= %s
                """,
                (threshold,),
            )
            for row in cur.fetchall():
                incidents.append(
                    {
                        "type": "feed_deactivated",
                        "title": f"Feed deactivated: {row['source_name']}",
                        "detail": f"{row['feed_url']} — {row['consecutive_failures']} consecutive failures",
                        "severity": "warning",
                    }
                )

            # Articles stuck in pending > 2 hours
            cur.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM articles
                WHERE extraction_status = 'pending'
                  AND fetched_at < NOW() - INTERVAL '2 hours'
                """
            )
            pending_stuck = cur.fetchone()["cnt"]
            if pending_stuck > 0:
                incidents.append(
                    {
                        "type": "extraction_backlog",
                        "title": f"{pending_stuck} articles stuck in extraction",
                        "detail": "Articles pending for more than 2 hours",
                        "severity": "warning",
                    }
                )

            # Rewrite failures in last 24h
            cur.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM cluster_rewrites
                WHERE rewrite_failed = true
                  AND created_at >= NOW() - INTERVAL '24 hours'
                """
            )
            rewrite_failures = cur.fetchone()["cnt"]
            if rewrite_failures > 0:
                incidents.append(
                    {
                        "type": "rewrite_failures",
                        "title": f"{rewrite_failures} rewrite failures in last 24h",
                        "detail": "Cluster rewrites failed",
                        "severity": "warning",
                    }
                )

            # Job runs with error in last 24h
            cur.execute(
                """
                SELECT id, job_name, started_at, error_message
                FROM job_runs
                WHERE status = 'error'
                  AND started_at >= NOW() - INTERVAL '24 hours'
                ORDER BY started_at DESC
                """
            )
            for row in cur.fetchall():
                incidents.append(
                    {
                        "type": "job_error",
                        "title": f"Job failed: {row['job_name']}",
                        "detail": row["error_message"] or "Unknown error",
                        "severity": "error",
                    }
                )
    finally:
        return_connection(conn)

    return incidents


def get_admin_articles(
    limit: int,
    offset: int,
    extraction_status: str | None = None,
    source_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return articles for admin view with cluster_id and source_name."""
    conn = get_connection()
    try:
        conditions: list[str] = []
        params: list[Any] = []
        if extraction_status:
            conditions.append("a.extraction_status = %s")
            params.append(extraction_status)
        if source_id:
            conditions.append("a.source_id = %s")
            params.append(source_id)
        where_clause = " AND ".join(conditions) if conditions else "TRUE"
        params.extend([limit, offset])

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT a.id, a.title, a.url, a.source_id, a.published_at,
                       a.fetched_at, a.extraction_status, a.extraction_method,
                       ca.cluster_id::text AS cluster_id,
                       ns.name AS source_name
                FROM articles a
                LEFT JOIN news_sources ns ON ns.id = a.source_id
                LEFT JOIN cluster_articles ca ON ca.article_id = a.id
                WHERE {where_clause}
                ORDER BY a.fetched_at DESC NULLS LAST
                LIMIT %s OFFSET %s
                """,
                params,
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        return_connection(conn)


def get_admin_articles_count(
    extraction_status: str | None = None,
    source_id: str | None = None,
) -> int:
    """Return total article count for admin pagination."""
    conn = get_connection()
    try:
        conditions: list[str] = []
        params: list[Any] = []
        if extraction_status:
            conditions.append("extraction_status = %s")
            params.append(extraction_status)
        if source_id:
            conditions.append("source_id = %s")
            params.append(source_id)
        where_clause = " AND ".join(conditions) if conditions else "TRUE"

        with conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM articles WHERE {where_clause}",
                params,
            )
            row = cur.fetchone()
            return row[0] if row else 0
    finally:
        return_connection(conn)


def get_admin_clusters(limit: int, offset: int) -> list[dict[str, Any]]:
    """Return clusters with article_count and sample_titles for admin view."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT c.id::text AS cluster_id, c.created_at,
                       COUNT(ca.article_id) AS article_count,
                       (
                         SELECT COALESCE(array_agg(t.title), ARRAY[]::text[])
                         FROM (
                           SELECT a.title
                           FROM cluster_articles ca2
                           JOIN articles a ON a.id = ca2.article_id
                           WHERE ca2.cluster_id = c.id
                           ORDER BY ca2.position
                           LIMIT 3
                         ) t
                       ) AS sample_titles
                FROM clusters c
                LEFT JOIN cluster_articles ca ON ca.cluster_id = c.id
                GROUP BY c.id
                ORDER BY c.created_at DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            rows = cur.fetchall()
            result: list[dict[str, Any]] = []
            for row in rows:
                d = dict(row)
                # sample_titles may be a list from array_agg; limit to 3
                titles = d.get("sample_titles")
                if titles is not None and not isinstance(titles, list):
                    titles = list(titles) if titles else []
                d["sample_titles"] = (titles or [])[:3]
                result.append(d)
            return result
    finally:
        return_connection(conn)


def get_admin_clusters_count() -> int:
    """Return total cluster count for admin pagination."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM clusters")
            row = cur.fetchone()
            return row[0] if row else 0
    finally:
        return_connection(conn)


def get_admin_cluster_articles(cluster_id: str) -> list[dict[str, Any]]:
    """Return articles in a cluster with source_name for admin cluster detail view."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT a.id, a.title, a.url, a.source_id, ca.position,
                       ns.name AS source_name
                FROM articles a
                JOIN cluster_articles ca ON ca.article_id = a.id
                LEFT JOIN news_sources ns ON ns.id = a.source_id
                WHERE ca.cluster_id = %s::uuid
                ORDER BY ca.position
                """,
                (cluster_id,),
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        return_connection(conn)
