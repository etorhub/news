"""Tests for article_service feed logic."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from app.services.article_service import get_feed


def test_get_feed_multi_source_ranks_above_singleton() -> None:
    """Multi-source clusters appear before singletons regardless of recency."""
    now = datetime.now(UTC)
    one_hour_ago = now - timedelta(hours=1)

    # Singleton (1 source) - very fresh
    cluster_singleton = {
        "cluster_id": "c-singleton",
        "articles": [
            {
                "id": "a1",
                "source_id": "s1",
                "published_at": now,
                "url": "https://s1.com/1",
                "title": "Singleton",
            },
        ],
    }
    # Multi-source (2 sources) - slightly older
    cluster_multi = {
        "cluster_id": "c-multi",
        "articles": [
            {
                "id": "a2",
                "source_id": "s1",
                "published_at": one_hour_ago,
                "url": "https://s1.com/2",
                "title": "Multi",
            },
            {
                "id": "a3",
                "source_id": "s2",
                "published_at": one_hour_ago,
                "url": "https://s2.com/1",
                "title": "Multi",
            },
        ],
    }

    sources = {
        "s1": {"id": "s1", "name": "Source 1", "topics": ["politics"]},
        "s2": {"id": "s2", "name": "Source 2", "topics": ["politics"]},
    }

    with (
        patch("app.services.article_service.profile_service") as mock_ps,
        patch("app.services.article_service.load_sources") as mock_load_sources,
        patch("app.services.article_service.load_config") as mock_load_config,
        patch("app.services.article_service.db_clusters") as mock_db,
    ):
        mock_ps.get_profile_with_selections.return_value = {
            "source_ids": ["s1", "s2"],
            "topic_ids": ["politics"],
        }
        mock_ps.compute_profile_hash.return_value = "hash1"
        mock_load_sources.return_value = list(sources.values())
        mock_load_config.return_value = {
            "processing": {"cluster_window_hours": 24, "articles_per_day": 10},
            "relevance": {"min_sources": 2},
        }
        mock_db.get_clusters_with_articles_in_window.return_value = [
            {"cluster_id": "c-singleton"},
            {"cluster_id": "c-multi"},
        ]
        mock_db.get_articles_in_cluster.side_effect = [
            cluster_singleton["articles"],
            cluster_multi["articles"],
        ]
        mock_db.get_cluster_rewrites.return_value = {
            "c-singleton": {"title": "Singleton", "summary": "", "full_text": "Text"},
            "c-multi": {"title": "Multi", "summary": "", "full_text": "Text"},
        }

        feed, _ = get_feed(user_id=1)

        ids = [item["id"] for item in feed]
        assert ids.index("c-multi") < ids.index("c-singleton")


def test_get_feed_backfill_when_few_multi_source() -> None:
    """Fallback singletons fill feed when fewer multi-source clusters than limit."""
    now = datetime.now(UTC)
    sources = {
        "s1": {"id": "s1", "name": "Source 1", "topics": ["politics"]},
        "s2": {"id": "s2", "name": "Source 2", "topics": ["politics"]},
    }

    # One multi-source cluster, two singletons; limit 3
    cluster_multi = {
        "cluster_id": "c-multi",
        "articles": [
            {"id": "a1", "source_id": "s1", "published_at": now, "url": "u1", "title": "M"},
            {"id": "a2", "source_id": "s2", "published_at": now, "url": "u2", "title": "M"},
        ],
    }
    art_s1 = {"id": "a3", "source_id": "s1", "published_at": now, "url": "u3", "title": "S1"}
    art_s2 = {"id": "a4", "source_id": "s2", "published_at": now, "url": "u4", "title": "S2"}
    cluster_s1 = {"cluster_id": "c-s1", "articles": [art_s1]}
    cluster_s2 = {"cluster_id": "c-s2", "articles": [art_s2]}

    with (
        patch("app.services.article_service.profile_service") as mock_ps,
        patch("app.services.article_service.load_sources") as mock_load_sources,
        patch("app.services.article_service.load_config") as mock_load_config,
        patch("app.services.article_service.db_clusters") as mock_db,
    ):
        mock_ps.get_profile_with_selections.return_value = {
            "source_ids": ["s1", "s2"],
            "topic_ids": ["politics"],
        }
        mock_ps.compute_profile_hash.return_value = "hash1"
        mock_load_sources.return_value = list(sources.values())
        mock_load_config.return_value = {
            "processing": {"cluster_window_hours": 24, "articles_per_day": 3},
            "relevance": {"min_sources": 2},
        }
        mock_db.get_clusters_with_articles_in_window.return_value = [
            {"cluster_id": "c-multi"},
            {"cluster_id": "c-s1"},
            {"cluster_id": "c-s2"},
        ]
        mock_db.get_articles_in_cluster.side_effect = [
            cluster_multi["articles"],
            cluster_s1["articles"],
            cluster_s2["articles"],
        ]
        mock_db.get_cluster_rewrites.return_value = {
            "c-multi": {"title": "Multi", "summary": "", "full_text": "T"},
            "c-s1": {"title": "S1", "summary": "", "full_text": "T"},
            "c-s2": {"title": "S2", "summary": "", "full_text": "T"},
        }

        feed, _ = get_feed(user_id=1)

        assert len(feed) == 3
        assert feed[0]["id"] == "c-multi"
        assert feed[1]["id"] in ("c-s1", "c-s2")
        assert feed[2]["id"] in ("c-s1", "c-s2")


def test_get_feed_min_sources_one_disables_filter() -> None:
    """min_sources: 1 treats all clusters as primary (backward compatible)."""
    now = datetime.now(UTC)
    art = {"id": "a1", "source_id": "s1", "published_at": now, "url": "u1", "title": "T"}
    cluster_singleton = {"cluster_id": "c1", "articles": [art]}

    sources = {"s1": {"id": "s1", "name": "Source 1", "topics": ["politics"]}}

    with (
        patch("app.services.article_service.profile_service") as mock_ps,
        patch("app.services.article_service.load_sources") as mock_load_sources,
        patch("app.services.article_service.load_config") as mock_load_config,
        patch("app.services.article_service.db_clusters") as mock_db,
    ):
        mock_ps.get_profile_with_selections.return_value = {
            "source_ids": ["s1"],
            "topic_ids": ["politics"],
        }
        mock_ps.compute_profile_hash.return_value = "hash1"
        mock_load_sources.return_value = list(sources.values())
        mock_load_config.return_value = {
            "processing": {"cluster_window_hours": 24, "articles_per_day": 10},
            "relevance": {"min_sources": 1},
        }
        mock_db.get_clusters_with_articles_in_window.return_value = [
            {"cluster_id": "c1"},
        ]
        mock_db.get_articles_in_cluster.return_value = cluster_singleton["articles"]
        mock_db.get_cluster_rewrites.return_value = {
            "c1": {"title": "Title", "summary": "", "full_text": "Text"},
        }

        feed, _ = get_feed(user_id=1)

        assert len(feed) == 1
        assert feed[0]["id"] == "c1"
