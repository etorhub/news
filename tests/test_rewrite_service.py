"""Tests for rewrite service."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.rewrite_service import (
    RewriteReport,
    _parse_cluster_llm_response,
    rewrite_cluster,
    run_rewrite_batch,
)


def test_parse_cluster_llm_response_happy() -> None:
    """_parse_cluster_llm_response extracts title, summary and full text."""
    text = """TITLE:
Power outage affects 500 homes.

SUMMARY:
First sentence. Second sentence. Third sentence.

FULL:
This is the full simplified article. Short sentences. Simple words."""
    title, summary, full = _parse_cluster_llm_response(text)
    assert "Power outage" in title
    assert "First sentence" in summary
    assert "This is the full simplified article" in full


def test_parse_cluster_llm_response_missing_title_raises() -> None:
    """_parse_cluster_llm_response raises ValueError when TITLE: missing."""
    text = "SUMMARY:\nS\nFULL:\nF"
    with pytest.raises(ValueError, match="missing TITLE"):
        _parse_cluster_llm_response(text)


def test_parse_cluster_llm_response_missing_full_raises() -> None:
    """_parse_cluster_llm_response raises ValueError when FULL: missing."""
    text = "TITLE:\nT\nSUMMARY:\nS"
    with pytest.raises(ValueError, match="TITLE:, SUMMARY:, or FULL:"):
        _parse_cluster_llm_response(text)


def test_parse_cluster_llm_response_empty_sections_raises() -> None:
    """_parse_cluster_llm_response raises ValueError when sections are empty."""
    text = "TITLE:\n\nSUMMARY:\n\nFULL:\n"
    with pytest.raises(ValueError, match="Empty"):
        _parse_cluster_llm_response(text)


def test_rewrite_cluster_empty_articles_stores_failed() -> None:
    """rewrite_cluster stores rewrite_failed=True when articles have no text."""
    with (
        patch("app.services.rewrite_service.db_clusters") as mock_db,
        patch("app.services.rewrite_service.profile_service") as mock_ps,
    ):
        mock_ps.compute_profile_hash.return_value = "abc123"
        articles = [{"id": "art1", "raw_text": "", "full_text": None}]
        profile = {
            "language": "ca",
            "rewrite_tone": "Simple.",
            "filter_negative": False,
        }
        config = {}
        result = rewrite_cluster("cluster-1", articles, profile, config)
        assert result is False
        mock_db.insert_cluster_rewrite.assert_called_once_with(
            cluster_id="cluster-1",
            profile_hash="abc123",
            title=None,
            summary=None,
            full_text=None,
            rewrite_failed=True,
            error_message="Articles have no full_text or raw_text",
        )


def test_rewrite_cluster_success_stores_rewrite() -> None:
    """rewrite_cluster stores title, summary and full_text on success."""
    with (
        patch("app.services.rewrite_service.db_clusters") as mock_db,
        patch("app.services.rewrite_service.profile_service") as mock_ps,
        patch("app.services.rewrite_service.get_provider") as mock_get,
    ):
        mock_ps.compute_profile_hash.return_value = "hash1"
        mock_provider = MagicMock()
        mock_provider.complete.return_value = """TITLE:
Power outage in Barcelona.

SUMMARY:
One. Two. Three.

FULL:
Simplified article here."""
        mock_get.return_value = mock_provider

        articles = [
            {
                "id": "art1",
                "raw_text": "Original long article text.",
                "full_text": None,
            },
        ]
        profile = {
            "language": "ca",
            "rewrite_tone": "Simple.",
            "filter_negative": False,
        }
        config = {"processing": {"summary_sentences": 3}}

        result = rewrite_cluster("cluster-1", articles, profile, config)
        assert result is True
        mock_db.insert_cluster_rewrite.assert_called_once_with(
            cluster_id="cluster-1",
            profile_hash="hash1",
            title="Power outage in Barcelona.",
            summary="One. Two. Three.",
            full_text="Simplified article here.",
            rewrite_failed=False,
        )


def test_rewrite_cluster_provider_error_stores_failed() -> None:
    """rewrite_cluster stores rewrite_failed=True when provider raises."""
    from app.llm.provider import LLMProviderError

    with (
        patch("app.services.rewrite_service.db_clusters") as mock_db,
        patch("app.services.rewrite_service.profile_service") as mock_ps,
        patch("app.services.rewrite_service.get_provider") as mock_get,
    ):
        mock_ps.compute_profile_hash.return_value = "hash1"
        mock_provider = MagicMock()
        mock_provider.complete.side_effect = LLMProviderError("API down")
        mock_get.return_value = mock_provider

        articles = [{"id": "art1", "raw_text": "Some text", "full_text": None}]
        profile = {
            "language": "ca",
            "rewrite_tone": "Simple.",
            "filter_negative": False,
        }
        config = {}

        result = rewrite_cluster("cluster-1", articles, profile, config)
        assert result is False
        mock_db.insert_cluster_rewrite.assert_called_once_with(
            cluster_id="cluster-1",
            profile_hash="hash1",
            title=None,
            summary=None,
            full_text=None,
            rewrite_failed=True,
            error_message="API down",
        )


def test_run_rewrite_batch_empty_profiles() -> None:
    """run_rewrite_batch returns zero counts when no profiles exist."""
    with patch("app.services.rewrite_service.db_users") as mock_users:
        mock_users.get_distinct_rewrite_profiles.return_value = []
        config = {"schedule": {"rewrite_batch_size": 10}}
        report = run_rewrite_batch(config)
        assert report == RewriteReport(
            profiles_processed=0,
            clusters_attempted=0,
            clusters_succeeded=0,
            clusters_failed=0,
        )


def test_run_rewrite_batch_counts() -> None:
    """run_rewrite_batch returns correct counts for mixed success/failure."""
    with (
        patch("app.services.rewrite_service.db_users") as mock_users,
        patch("app.services.rewrite_service.db_clusters") as mock_clusters,
        patch("app.services.rewrite_service.rewrite_cluster") as mock_rewrite,
    ):
        mock_users.get_distinct_rewrite_profiles.return_value = [
            {
                "language": "ca",
                "rewrite_tone": "Simple",
                "filter_negative": False,
            },
        ]
        mock_clusters.get_clusters_needing_rewrite.return_value = [
            {"cluster_id": "c1"},
            {"cluster_id": "c2"},
        ]
        mock_clusters.get_articles_in_cluster.side_effect = [
            [{"id": "a1", "raw_text": "t1", "full_text": None}],
            [{"id": "a2", "raw_text": "t2", "full_text": None}],
        ]
        mock_rewrite.side_effect = [True, False]

        config = {"schedule": {"rewrite_batch_size": 10}}
        report = run_rewrite_batch(config)

        assert report.profiles_processed == 1
        assert report.clusters_attempted == 2
        assert report.clusters_succeeded == 1
        assert report.clusters_failed == 1
