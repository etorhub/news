"""CRUD operations for clusters, cluster_articles, cluster_rewrites."""

import uuid
from datetime import datetime
from typing import Any

import psycopg2.extras

from app.db.connection import get_connection, return_connection


def insert_cluster(article_ids: list[str]) -> str:
    """Create a cluster with the given articles. Returns cluster_id (UUID string)."""
    if not article_ids:
        raise ValueError("Cannot create cluster with no articles")
    cluster_id = str(uuid.uuid4())
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO clusters (id) VALUES (%s::uuid)",
                (cluster_id,),
            )
            for pos, aid in enumerate(article_ids):
                cur.execute(
                    """
                    INSERT INTO cluster_articles (cluster_id, article_id, position)
                    VALUES (%s::uuid, %s, %s)
                    """,
                    (cluster_id, aid, pos),
                )
        conn.commit()
        return cluster_id
    finally:
        return_connection(conn)


def get_articles_in_cluster(cluster_id: str) -> list[dict[str, Any]]:
    """Return articles in a cluster, ordered by position."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT a.*, ca.position
                FROM articles a
                JOIN cluster_articles ca ON ca.article_id = a.id
                WHERE ca.cluster_id = %s::uuid
                ORDER BY ca.position
                """,
                (cluster_id,),
            )
            rows = cur.fetchall()
            return [dict(row) for row in rows]
    finally:
        return_connection(conn)


def get_cluster_ids_for_articles(article_ids: list[str]) -> dict[str, str]:
    """Return mapping article_id -> cluster_id for articles that are in a cluster."""
    if not article_ids:
        return {}
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT article_id, cluster_id::text
                FROM cluster_articles
                WHERE article_id = ANY(%s)
                """,
                (article_ids,),
            )
            return {row["article_id"]: row["cluster_id"] for row in cur.fetchall()}
    finally:
        return_connection(conn)


def get_clusters_with_articles_in_window(
    since: datetime | None,
    source_ids: set[str] | None = None,
    topic_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Return clusters that have at least one article.

    If since is not None, only clusters with articles published since that time.
    If since is None, return all clusters (ordered by most recent article).
    Source/topic filtering is done at the service layer.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if since is not None:
                cur.execute(
                    """
                    SELECT DISTINCT c.id::text as cluster_id, c.created_at
                    FROM clusters c
                    JOIN cluster_articles ca ON ca.cluster_id = c.id
                    JOIN articles a ON a.id = ca.article_id
                    WHERE a.published_at >= %s
                    ORDER BY c.created_at DESC
                    """,
                    (since,),
                )
            else:
                cur.execute(
                    """
                    SELECT DISTINCT c.id::text as cluster_id, c.created_at
                    FROM clusters c
                    JOIN cluster_articles ca ON ca.cluster_id = c.id
                    JOIN articles a ON a.id = ca.article_id
                    ORDER BY c.created_at DESC
                    """
                )
            return [dict(row) for row in cur.fetchall()]
    finally:
        return_connection(conn)


def get_clusters_needing_rewrite_for_variant(
    style: str,
    language: str,
    since: datetime | None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return clusters that have no rewrite for this (style, language) variant.

    If since is not None, only clusters with articles published since that time.
    If since is None, return all clusters needing this variant.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if since is not None:
                cur.execute(
                    """
                    SELECT c.id::text as cluster_id
                    FROM clusters c
                    JOIN cluster_articles ca ON ca.cluster_id = c.id
                    JOIN articles a ON a.id = ca.article_id
                    LEFT JOIN cluster_rewrites cr ON cr.cluster_id = c.id
                        AND cr.style = %s AND cr.language = %s
                    WHERE a.published_at >= %s AND cr.cluster_id IS NULL
                    GROUP BY c.id
                    ORDER BY MAX(a.published_at) DESC
                    """,
                    (style, language, since),
                )
            else:
                cur.execute(
                    """
                    SELECT c.id::text as cluster_id
                    FROM clusters c
                    JOIN cluster_articles ca ON ca.cluster_id = c.id
                    JOIN articles a ON a.id = ca.article_id
                    LEFT JOIN cluster_rewrites cr ON cr.cluster_id = c.id
                        AND cr.style = %s AND cr.language = %s
                    WHERE cr.cluster_id IS NULL
                    GROUP BY c.id
                    ORDER BY MAX(a.published_at) DESC
                    """,
                    (style, language),
                )
            rows = cur.fetchall()
            if limit is not None:
                rows = rows[:limit]
            return [dict(row) for row in rows]
    finally:
        return_connection(conn)


def insert_cluster_rewrite(
    cluster_id: str,
    style: str,
    language: str,
    title: str | None,
    summary: str | None,
    full_text: str | None,
    rewrite_failed: bool = False,
    error_message: str | None = None,
) -> None:
    """Insert or update a cluster rewrite for (cluster_id, style, language)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO cluster_rewrites (
                    cluster_id, style, language, title, summary, full_text,
                    rewrite_failed, error_message
                )
                VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (cluster_id, style, language)
                DO UPDATE SET
                    title = EXCLUDED.title,
                    summary = EXCLUDED.summary,
                    full_text = EXCLUDED.full_text,
                    rewrite_failed = EXCLUDED.rewrite_failed,
                    error_message = EXCLUDED.error_message
                """,
                (
                    cluster_id,
                    style,
                    language,
                    title,
                    summary,
                    full_text,
                    rewrite_failed,
                    error_message,
                ),
            )
        conn.commit()
    finally:
        return_connection(conn)


def get_cluster_rewrites(
    cluster_ids: list[str],
    style: str,
    language: str,
) -> dict[str, dict[str, Any]]:
    """Return rewrites for cluster_ids and (style, language), keyed by cluster_id."""
    if not cluster_ids:
        return {}
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT cluster_id::text, title, summary, full_text, rewrite_failed
                FROM cluster_rewrites
                WHERE style = %s AND language = %s AND cluster_id::text = ANY(%s)
                """,
                (style, language, cluster_ids),
            )
            return {row["cluster_id"]: dict(row) for row in cur.fetchall()}
    finally:
        return_connection(conn)


def cluster_exists(cluster_id: str) -> bool:
    """Return True if cluster exists."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM clusters WHERE id = %s::uuid", (cluster_id,))
            return cur.fetchone() is not None
    finally:
        return_connection(conn)


