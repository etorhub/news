"""Tests for rewrite service."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.rewrite_service import (
    RewriteReport,
    _parse_llm_response,
    rewrite_one,
    run_rewrite_batch,
)


def test_parse_llm_response_happy() -> None:
    """_parse_llm_response extracts summary and full text."""
    text = """SUMMARY:
First sentence. Second sentence. Third sentence.

FULL:
This is the full simplified article. Short sentences. Simple words."""
    summary, full = _parse_llm_response(text)
    assert "First sentence" in summary
    assert "Second sentence" in summary
    assert "This is the full simplified article" in full


def test_parse_llm_response_missing_summary_raises() -> None:
    """_parse_llm_response raises ValueError when SUMMARY: missing."""
    text = "FULL:\nSome content"
    with pytest.raises(ValueError, match="missing SUMMARY"):
        _parse_llm_response(text)


def test_parse_llm_response_missing_full_raises() -> None:
    """_parse_llm_response raises ValueError when FULL: missing."""
    text = "SUMMARY:\nSome summary"
    with pytest.raises(ValueError, match="SUMMARY: or FULL:"):
        _parse_llm_response(text)


def test_parse_llm_response_empty_sections_raises() -> None:
    """_parse_llm_response raises ValueError when sections are empty."""
    text = "SUMMARY:\n\nFULL:\n"
    with pytest.raises(ValueError, match="Empty"):
        _parse_llm_response(text)


def test_rewrite_one_empty_article_stores_failed() -> None:
    """rewrite_one stores rewrite_failed=True when article has no text."""
    with (
        patch("app.services.rewrite_service.db_rewrites") as mock_db,
        patch("app.services.rewrite_service.profile_service") as mock_ps,
    ):
            mock_ps.compute_profile_hash.return_value = "abc123"
            article = {"id": "art1", "raw_text": "", "full_text": None}
            profile = {
                "language": "ca",
                "rewrite_tone": "Simple.",
                "filter_negative": False,
            }
            config = {}
            result = rewrite_one("art1", article, profile, config)
            assert result is False
            mock_db.insert_rewrite.assert_called_once_with(
                article_id="art1",
                profile_hash="abc123",
                summary=None,
                full_text=None,
                rewrite_failed=True,
            )


def test_rewrite_one_success_stores_rewrite() -> None:
    """rewrite_one stores summary and full_text on success."""
    with (
        patch("app.services.rewrite_service.db_rewrites") as mock_db,
        patch("app.services.rewrite_service.profile_service") as mock_ps,
        patch("app.services.rewrite_service.get_provider") as mock_get,
    ):
        mock_ps.compute_profile_hash.return_value = "hash1"
        mock_provider = MagicMock()
        mock_provider.complete.return_value = """SUMMARY:
One. Two. Three.

FULL:
Simplified article here."""
        mock_get.return_value = mock_provider

        article = {
            "id": "art1",
            "raw_text": "Original long article text.",
            "full_text": None,
        }
        profile = {
            "language": "ca",
            "rewrite_tone": "Simple.",
            "filter_negative": False,
        }
        config = {"processing": {"summary_sentences": 3}}

        result = rewrite_one("art1", article, profile, config)
        assert result is True
        mock_db.insert_rewrite.assert_called_once_with(
                    article_id="art1",
                    profile_hash="hash1",
            summary="One. Two. Three.",
            full_text="Simplified article here.",
            rewrite_failed=False,
        )


def test_rewrite_one_provider_error_stores_failed() -> None:
    """rewrite_one stores rewrite_failed=True when provider raises."""
    from app.llm.provider import LLMProviderError

    with (
        patch("app.services.rewrite_service.db_rewrites") as mock_db,
        patch("app.services.rewrite_service.profile_service") as mock_ps,
        patch("app.services.rewrite_service.get_provider") as mock_get,
    ):
        mock_ps.compute_profile_hash.return_value = "hash1"
        mock_provider = MagicMock()
        mock_provider.complete.side_effect = LLMProviderError("API down")
        mock_get.return_value = mock_provider

        article = {"id": "art1", "raw_text": "Some text", "full_text": None}
        profile = {
            "language": "ca",
            "rewrite_tone": "Simple.",
            "filter_negative": False,
        }
        config = {}

        result = rewrite_one("art1", article, profile, config)
        assert result is False
        mock_db.insert_rewrite.assert_called_once_with(
            article_id="art1",
            profile_hash="hash1",
            summary=None,
            full_text=None,
            rewrite_failed=True,
        )


def test_run_rewrite_batch_empty_profiles() -> None:
    """run_rewrite_batch returns zero counts when no profiles exist."""
    with patch("app.services.rewrite_service.db_users") as mock_users:
        mock_users.get_distinct_rewrite_profiles.return_value = []
        config = {"schedule": {"rewrite_batch_size": 10}}
        report = run_rewrite_batch(config)
        assert report == RewriteReport(
            profiles_processed=0,
            articles_attempted=0,
            articles_succeeded=0,
            articles_failed=0,
        )


def test_run_rewrite_batch_counts() -> None:
    """run_rewrite_batch returns correct counts for mixed success/failure."""
    with (
        patch("app.services.rewrite_service.db_users") as mock_users,
        patch("app.services.rewrite_service.db_rewrites") as mock_rewrites,
        patch("app.services.rewrite_service.rewrite_one") as mock_rewrite,
    ):
        mock_users.get_distinct_rewrite_profiles.return_value = [
            {
                "language": "ca",
                "rewrite_tone": "Simple",
                "filter_negative": False,
            },
        ]
        mock_rewrites.get_articles_needing_rewrite.return_value = [
            {"id": "a1", "raw_text": "t1", "full_text": None},
            {"id": "a2", "raw_text": "t2", "full_text": None},
        ]
        mock_rewrite.side_effect = [True, False]

        config = {"schedule": {"rewrite_batch_size": 10}}
        report = run_rewrite_batch(config)

        assert report.profiles_processed == 1
        assert report.articles_attempted == 2
        assert report.articles_succeeded == 1
        assert report.articles_failed == 1
