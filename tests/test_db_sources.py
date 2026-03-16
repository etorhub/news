"""Tests for db/sources module.

Uses real database when DATABASE_URL is set (e.g. in Docker).
Skips when no database available.
"""

import pytest

from app.db import sources as sources_db


def _has_db() -> bool:
    """Check if we can connect to the database."""
    try:
        conn = sources_db.get_connection()
        sources_db.return_connection(conn)
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _has_db(), reason="Database not available")
def test_upsert_source_and_get() -> None:
    """Upsert source and retrieve it."""
    source = {
        "id": "test_source_xyz",
        "domain": "test.example.com",
        "name": "Test Source",
        "homepage_url": "https://test.example.com/",
        "country_code": "ES",
        "languages": ["ca"],
    }
    sources_db.upsert_source(source)
    try:
        retrieved = sources_db.get_source_by_id("test_source_xyz")
        assert retrieved is not None
        assert retrieved["name"] == "Test Source"
        assert retrieved["domain"] == "test.example.com"
    finally:
        # Cleanup: delete via raw connection (no delete function in API)
        conn = sources_db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM source_feeds WHERE source_id = %s",
                    ("test_source_xyz",),
                )
                cur.execute(
                    "DELETE FROM news_sources WHERE id = %s",
                    ("test_source_xyz",),
                )
            conn.commit()
        finally:
            sources_db.return_connection(conn)


@pytest.mark.skipif(not _has_db(), reason="Database not available")
def test_get_all_sources_returns_list() -> None:
    """get_all_sources returns a list (may be empty)."""
    sources = sources_db.get_all_sources()
    assert isinstance(sources, list)
