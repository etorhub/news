"""CRUD operations for the rewrites table."""

from typing import Any

import psycopg2.extras

from app.db.connection import get_connection, return_connection


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
