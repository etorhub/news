"""Tests for discovery scoring module."""

from app.discovery.scoring import calculate_quality_score


def test_calculate_quality_score_perfect() -> None:
    """Perfect inputs yield high score."""
    score = calculate_quality_score(
        feed_completeness_pct=100.0,
        feed_type="rss",
        articles_per_day=10.0,
        https_ok=True,
    )
    assert score >= 90
    assert score <= 100


def test_calculate_quality_score_zero_frequency() -> None:
    """Zero articles per day still gives some score from other factors."""
    score = calculate_quality_score(
        feed_completeness_pct=80.0,
        feed_type="rss",
        articles_per_day=0.0,
        https_ok=True,
    )
    assert score > 0
    assert score < 100


def test_calculate_quality_score_no_https() -> None:
    """HTTPS failure reduces score."""
    score_https = calculate_quality_score(
        feed_completeness_pct=100.0,
        feed_type="rss",
        articles_per_day=10.0,
        https_ok=True,
    )
    score_no_https = calculate_quality_score(
        feed_completeness_pct=100.0,
        feed_type="rss",
        articles_per_day=10.0,
        https_ok=False,
    )
    assert score_no_https < score_https


def test_calculate_quality_score_atom_vs_rss() -> None:
    """Atom and RSS get same consumption score."""
    score_rss = calculate_quality_score(
        feed_completeness_pct=50.0,
        feed_type="rss",
        articles_per_day=5.0,
        https_ok=True,
    )
    score_atom = calculate_quality_score(
        feed_completeness_pct=50.0,
        feed_type="atom",
        articles_per_day=5.0,
        https_ok=True,
    )
    assert score_rss == score_atom


def test_calculate_quality_score_bounds() -> None:
    """Score is always 0-100."""
    score = calculate_quality_score(
        feed_completeness_pct=0.0,
        feed_type="unknown",
        articles_per_day=0.0,
        https_ok=False,
    )
    assert 0 <= score <= 100
