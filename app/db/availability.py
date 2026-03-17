"""DB operations for source feed availability checks."""

from typing import Any

import psycopg2.extras

from app.db.connection import get_connection, return_connection


def insert_availability_check(
    feed_id: int,
    *,
    is_available: bool,
    http_status: int | None = None,
    response_time_ms: int | None = None,
    error_message: str | None = None,
) -> None:
    """Insert an availability check result and update the feed's cached status."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO source_availability_checks (
                    feed_id, is_available, http_status, response_time_ms, error_message
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (feed_id, is_available, http_status, response_time_ms, error_message),
            )
            cur.execute(
                """
                UPDATE source_feeds
                SET is_available = %s, last_availability_check_at = NOW()
                WHERE id = %s
                """,
                (is_available, feed_id),
            )
        conn.commit()
    finally:
        return_connection(conn)


def get_availability_history(feed_id: int, limit: int = 20) -> list[dict[str, Any]]:
    """Return recent availability checks for a feed, newest first."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, feed_id, checked_at, is_available,
                       http_status, response_time_ms, error_message
                FROM source_availability_checks
                WHERE feed_id = %s
                ORDER BY checked_at DESC
                LIMIT %s
                """,
                (feed_id, limit),
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        return_connection(conn)
