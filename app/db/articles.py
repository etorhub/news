"""CRUD operations for the articles table."""

import hashlib
from datetime import datetime
from typing import Any

import psycopg2.extras

from app.db.connection import get_connection, return_connection


def _article_id(source_id: str, url: str) -> str:
    """Generate deterministic article id from source_id and url."""
    return hashlib.sha256(f"{source_id}:{url}".encode()).hexdigest()[:16]


def get_article_by_id(article_id: str) -> dict[str, Any] | None:
    """Return article dict or None if not found."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM articles WHERE id = %s", (article_id,))
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        return_connection(conn)


def insert_article(article: dict[str, Any]) -> bool:
    """Insert an article. Returns True if inserted, False if duplicate.

    Article dict must have: title, url, source_id. Optional: published_at,
    raw_text, full_text, guid. Id is generated from source_id:url.
    """
    article_id = _article_id(article["source_id"], article["url"])
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO articles (
                    id, title, url, source_id, published_at,
                    raw_text, full_text, guid
                )
                VALUES (
                    %(id)s, %(title)s, %(url)s, %(source_id)s, %(published_at)s,
                    %(raw_text)s, %(full_text)s, %(guid)s
                )
                ON CONFLICT (source_id, url) DO NOTHING
                """,
                {
                    "id": article_id,
                    "title": article["title"],
                    "url": article["url"],
                    "source_id": article["source_id"],
                    "published_at": article.get("published_at"),
                    "raw_text": article.get("raw_text"),
                    "full_text": article.get("full_text"),
                    "guid": article.get("guid"),
                },
            )
            inserted = bool(cur.rowcount > 0)
        conn.commit()
        return inserted
    finally:
        return_connection(conn)


def article_exists(source_id: str, url: str) -> bool:
    """Return True if an article with this source_id and url exists."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM articles WHERE source_id = %s AND url = %s",
                (source_id, url),
            )
            return cur.fetchone() is not None
    finally:
        return_connection(conn)


def get_recent_articles(
    since: datetime,
    source_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return articles published on or after since, optionally filtered by source."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if source_id:
                cur.execute(
                    """
                    SELECT * FROM articles
                    WHERE published_at >= %s AND source_id = %s
                    ORDER BY published_at DESC
                    """,
                    (since, source_id),
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM articles
                    WHERE published_at >= %s
                    ORDER BY published_at DESC
                    """,
                    (since,),
                )
            return [dict(row) for row in cur.fetchall()]
    finally:
        return_connection(conn)
