"""CRUD operations for the rewrites table."""

from datetime import datetime
from typing import Any

import psycopg2.extras

from app.db.connection import get_connection, return_connection


def insert_rewrite(
    article_id: str,
    profile_hash: str,
    summary: str | None,
    full_text: str | None,
    rewrite_failed: bool = False,
) -> None:
    """Insert or update a rewrite. Upserts on (article_id, profile_hash)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rewrites (
                    article_id, profile_hash, summary, full_text, rewrite_failed
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (article_id, profile_hash)
                DO UPDATE SET
                    summary = EXCLUDED.summary,
                    full_text = EXCLUDED.full_text,
                    rewrite_failed = EXCLUDED.rewrite_failed
                """,
                (article_id, profile_hash, summary, full_text, rewrite_failed),
            )
        conn.commit()
    finally:
        return_connection(conn)


def get_articles_needing_rewrite(
    profile_hash: str,
    since: datetime,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return articles since given time with no rewrite for this profile_hash."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT a.* FROM articles a
                LEFT JOIN rewrites r ON r.article_id = a.id AND r.profile_hash = %s
                WHERE r.article_id IS NULL AND a.published_at >= %s
                ORDER BY a.published_at DESC
                """,
                (profile_hash, since),
            )
            rows = cur.fetchall()
            if limit is not None:
                rows = rows[:limit]
            return [dict(row) for row in rows]
    finally:
        return_connection(conn)


def get_rewrites_for_articles(
    article_ids: list[str], profile_hash: str
) -> dict[str, dict[str, Any]]:
    """Return rewrites for article_ids and profile_hash, keyed by article_id."""
    if not article_ids:
        return {}
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT article_id, summary, full_text, rewrite_failed
                FROM rewrites
                WHERE profile_hash = %s AND article_id = ANY(%s)
                """,
                (profile_hash, article_ids),
            )
            return {row["article_id"]: dict(row) for row in cur.fetchall()}
    finally:
        return_connection(conn)
