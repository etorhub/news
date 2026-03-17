"""Tests for extraction module."""

from unittest.mock import patch

import pytest

from app.db import articles as articles_db
from app.db.connection import get_connection, return_connection
from app.extraction.extractor import _domain_from_url, enrich_articles
from app.extraction.trafilatura import extract_article


def _has_db() -> bool:
    """Check if we can connect to the database."""
    try:
        conn = get_connection()
        return_connection(conn)
        return True
    except Exception:
        return False


def _cleanup_test_extraction_articles() -> None:
    """Remove test articles used by extraction tests."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM articles WHERE source_id = %s",
                ("test_extraction_src",),
            )
        conn.commit()
    finally:
        return_connection(conn)


def test_domain_from_url() -> None:
    """_domain_from_url extracts netloc from URL."""
    assert _domain_from_url("https://www.example.com/path") == "www.example.com"
    assert _domain_from_url("https://example.com") == "example.com"


@patch("app.extraction.trafilatura.trafilatura.fetch_url")
@patch("app.extraction.trafilatura.trafilatura.extract")
def test_extract_article_success(mock_extract, mock_fetch) -> None:
    """extract_article returns (text, og_image_url) when extraction succeeds."""
    mock_fetch.return_value = "<html><body><article>Hello world</article></body></html>"
    mock_extract.return_value = "Hello world"

    text, og_image = extract_article("https://example.com/article")
    assert text == "Hello world"
    assert og_image is None
    mock_fetch.assert_called_once()
    mock_extract.assert_called_once()


@patch("app.extraction.trafilatura.trafilatura.fetch_url")
def test_extract_article_fetch_fails(mock_fetch) -> None:
    """extract_article returns (None, None) when fetch fails."""
    mock_fetch.return_value = None

    text, og_image = extract_article("https://example.com/article")
    assert text is None
    assert og_image is None


@patch("app.extraction.trafilatura.trafilatura.fetch_url")
@patch("app.extraction.trafilatura.trafilatura.extract")
def test_extract_article_extract_returns_empty(mock_extract, mock_fetch) -> None:
    """extract_article returns (None, og_image) when extract returns empty."""
    mock_fetch.return_value = "<html></html>"
    mock_extract.return_value = None

    text, og_image = extract_article("https://example.com/article")
    assert text is None
    assert og_image is None


@patch("app.extraction.trafilatura.trafilatura.fetch_url")
@patch("app.extraction.trafilatura.trafilatura.extract")
def test_extract_article_extract_returns_whitespace(mock_extract, mock_fetch) -> None:
    """extract_article returns (None, None) when extract returns only whitespace."""
    mock_fetch.return_value = "<html></html>"
    mock_extract.return_value = "   \n  "

    text, og_image = extract_article("https://example.com/article")
    assert text is None
    assert og_image is None


@patch("app.extraction.trafilatura.trafilatura.fetch_url")
@patch("app.extraction.trafilatura.trafilatura.extract")
def test_extract_article_extracts_og_image(mock_extract, mock_fetch) -> None:
    """extract_article extracts og:image from HTML when present."""
    html_with_og = (
        '<html><head><meta property="og:image" content="https://example.com/og.jpg" />'
        "</head><body></body></html>"
    )
    mock_fetch.return_value = html_with_og
    mock_extract.return_value = "Article text"

    text, og_image = extract_article("https://example.com/article")
    assert text == "Article text"
    assert og_image == "https://example.com/og.jpg"


def test_enrich_articles_disabled_returns_empty_report() -> None:
    """enrich_articles returns zeros when extraction is disabled."""
    config = {"extraction": {"enabled": False}}
    report = enrich_articles(config)
    assert report.articles_checked == 0
    assert report.articles_extracted == 0
    assert report.articles_failed == 0
    assert report.articles_skipped == 0


@pytest.mark.skipif(not _has_db(), reason="Database not available")
def test_get_articles_needing_extraction() -> None:
    """get_articles_needing_extraction returns pending articles."""
    _cleanup_test_extraction_articles()
    article = {
        "source_id": "test_extraction_src",
        "title": "Pending Article",
        "url": "https://test.example.com/pending",
    }
    try:
        articles_db.insert_article(article)
        # New articles get extraction_status='pending' via server default
        candidates = articles_db.get_articles_needing_extraction(limit=10)
        found = next(
            (a for a in candidates if a["source_id"] == "test_extraction_src"), None
        )
        assert found is not None
        assert found["url"] == "https://test.example.com/pending"
    finally:
        _cleanup_test_extraction_articles()


@pytest.mark.skipif(not _has_db(), reason="Database not available")
def test_update_article_extraction() -> None:
    """update_article_extraction updates article with extraction result."""
    _cleanup_test_extraction_articles()
    article = {
        "source_id": "test_extraction_src",
        "title": "Update Test",
        "url": "https://test.example.com/update",
    }
    try:
        inserted = articles_db.insert_article(article)
        assert inserted is True
        art = articles_db.get_articles_needing_extraction(limit=1)
        assert len(art) >= 1
        article_id = art[0]["id"]

        articles_db.update_article_extraction(
            article_id, "Extracted full text.", "extracted", "trafilatura"
        )

        updated = articles_db.get_article_by_id(article_id)
        assert updated is not None
        assert updated["full_text"] == "Extracted full text."
        assert updated["extraction_status"] == "extracted"
        assert updated["extraction_method"] == "trafilatura"
        assert updated["extracted_at"] is not None
    finally:
        _cleanup_test_extraction_articles()
