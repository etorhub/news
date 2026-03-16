"""CRUD operations for news_sources and source_feeds tables."""

from typing import Any

import psycopg2.extras

from app.db.connection import get_connection, return_connection


def upsert_source(source: dict[str, Any]) -> None:
    """Insert or update a news source. Uses source id as conflict key."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO news_sources (
                    id, domain, name, description, homepage_url,
                    country_code, region, languages, quality_score,
                    is_verified, full_text_available, status, last_checked_at
                ) VALUES (
                    %(id)s, %(domain)s, %(name)s, %(description)s,
                    %(homepage_url)s, %(country_code)s, %(region)s,
                    %(languages)s, %(quality_score)s, %(is_verified)s,
                    %(full_text_available)s, %(status)s, %(last_checked_at)s
                )
                ON CONFLICT (id) DO UPDATE SET
                    domain = EXCLUDED.domain,
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    homepage_url = EXCLUDED.homepage_url,
                    country_code = EXCLUDED.country_code,
                    region = EXCLUDED.region,
                    languages = EXCLUDED.languages,
                    quality_score = COALESCE(
                        EXCLUDED.quality_score, news_sources.quality_score
                    ),
                    is_verified = EXCLUDED.is_verified,
                    full_text_available = EXCLUDED.full_text_available,
                    status = EXCLUDED.status,
                    last_checked_at = COALESCE(
                        EXCLUDED.last_checked_at, news_sources.last_checked_at
                    ),
                    updated_at = NOW()
                """,
                {
                    "id": source["id"],
                    "domain": source["domain"],
                    "name": source["name"],
                    "description": source.get("description"),
                    "homepage_url": source["homepage_url"],
                    "country_code": source["country_code"],
                    "region": source.get("region"),
                    "languages": source["languages"],
                    "quality_score": source.get("quality_score"),
                    "is_verified": source.get("is_verified", False),
                    "full_text_available": source.get("full_text_available", False),
                    "status": source.get("status", "active"),
                    "last_checked_at": source.get("last_checked_at"),
                },
            )
        conn.commit()
    finally:
        return_connection(conn)


def insert_feed(feed: dict[str, Any]) -> None:
    """Insert a source feed. Call delete_feeds_for_source first when re-seeding."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO source_feeds (
                    source_id, feed_type, feed_url, feed_label,
                    poll_interval_minutes, last_fetched_at, last_item_guid,
                    consecutive_failures, avg_articles_per_day, feed_active
                ) VALUES (
                    %(source_id)s, %(feed_type)s, %(feed_url)s, %(feed_label)s,
                    %(poll_interval_minutes)s, %(last_fetched_at)s, %(last_item_guid)s,
                    %(consecutive_failures)s, %(avg_articles_per_day)s, %(feed_active)s
                )
                """,
                {
                    "source_id": feed["source_id"],
                    "feed_type": feed["feed_type"],
                    "feed_url": feed["feed_url"],
                    "feed_label": feed.get("feed_label"),
                    "poll_interval_minutes": feed.get("poll_interval_minutes", 60),
                    "last_fetched_at": feed.get("last_fetched_at"),
                    "last_item_guid": feed.get("last_item_guid"),
                    "consecutive_failures": feed.get("consecutive_failures", 0),
                    "avg_articles_per_day": feed.get("avg_articles_per_day"),
                    "feed_active": feed.get("feed_active", True),
                },
            )
        conn.commit()
    finally:
        return_connection(conn)


def update_feed(
    feed_id: int,
    *,
    last_fetched_at: str | None = None,
    last_item_guid: str | None = None,
    consecutive_failures: int | None = None,
    avg_articles_per_day: float | None = None,
    feed_active: bool | None = None,
) -> None:
    """Update feed metadata. Pass only the fields to update."""
    # Build dynamic update - we only update non-None kwargs
    updates: list[str] = []
    params: dict[str, Any] = {"feed_id": feed_id}
    if last_fetched_at is not None:
        updates.append("last_fetched_at = %(last_fetched_at)s")
        params["last_fetched_at"] = last_fetched_at
    if last_item_guid is not None:
        updates.append("last_item_guid = %(last_item_guid)s")
        params["last_item_guid"] = last_item_guid
    if consecutive_failures is not None:
        updates.append("consecutive_failures = %(consecutive_failures)s")
        params["consecutive_failures"] = consecutive_failures
    if avg_articles_per_day is not None:
        updates.append("avg_articles_per_day = %(avg_articles_per_day)s")
        params["avg_articles_per_day"] = avg_articles_per_day
    if feed_active is not None:
        updates.append("feed_active = %(feed_active)s")
        params["feed_active"] = feed_active
    if not updates:
        return
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE source_feeds SET {', '.join(updates)} WHERE id = %(feed_id)s",
                params,
            )
        conn.commit()
    finally:
        return_connection(conn)


def delete_feeds_for_source(source_id: str) -> None:
    """Delete all feeds for a source. Used before re-seeding from YAML."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM source_feeds WHERE source_id = %s",
                (source_id,),
            )
        conn.commit()
    finally:
        return_connection(conn)


def get_all_sources(status: str = "active") -> list[dict[str, Any]]:
    """Return all sources, optionally filtered by status."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT * FROM news_sources
                   WHERE status = %s
                   ORDER BY quality_score DESC NULLS LAST, name""",
                (status,),
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        return_connection(conn)


def get_feeds_for_source(source_id: str) -> list[dict[str, Any]]:
    """Return all feeds for a source."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT * FROM source_feeds
                   WHERE source_id = %s
                   ORDER BY feed_label NULLS LAST""",
                (source_id,),
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        return_connection(conn)


def get_all_active_feeds() -> list[dict[str, Any]]:
    """Return all active feeds with their source info."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT sf.*, ns.domain, ns.name
                FROM source_feeds sf
                JOIN news_sources ns ON ns.id = sf.source_id
                WHERE sf.feed_active = TRUE AND ns.status = 'active'
                ORDER BY sf.source_id, sf.feed_label NULLS LAST
                """
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        return_connection(conn)


def update_source_score(source_id: str, score: float) -> None:
    """Update the quality score for a source."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE news_sources
                SET quality_score = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (score, source_id),
            )
        conn.commit()
    finally:
        return_connection(conn)


def log_discovery(entry: dict[str, Any]) -> None:
    """Insert a row into source_discovery_log."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO source_discovery_log (
                    source_id, discovery_run_id, target_location,
                    discovery_method, validation_result, rejected_reason
                ) VALUES (
                    %(source_id)s, %(discovery_run_id)s, %(target_location)s,
                    %(discovery_method)s, %(validation_result)s, %(rejected_reason)s
                )
                """,
                {
                    "source_id": entry.get("source_id"),
                    "discovery_run_id": entry["discovery_run_id"],
                    "target_location": entry["target_location"],
                    "discovery_method": entry.get("discovery_method"),
                    "validation_result": entry.get("validation_result"),
                    "rejected_reason": entry.get("rejected_reason"),
                },
            )
        conn.commit()
    finally:
        return_connection(conn)


def get_source_by_id(source_id: str) -> dict[str, Any] | None:
    """Return a single source by id, or None if not found."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM news_sources WHERE id = %s", (source_id,))
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        return_connection(conn)
