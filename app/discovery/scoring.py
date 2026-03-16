"""Quality scoring for news sources."""

CONSUMPTION_SCORES: dict[str, int] = {
    "json_api": 100,
    "rss": 80,
    "atom": 80,
    "sitemap": 60,
    "google_news_rss": 55,
    "scrape_structured": 40,
    "scrape_html": 20,
}

WEIGHTS: dict[str, float] = {
    "feed_completeness": 0.30,
    "consumption_method": 0.30,
    "publication_frequency": 0.25,
    "https": 0.15,
}


def calculate_quality_score(
    *,
    feed_completeness_pct: float = 0.0,
    feed_type: str = "rss",
    articles_per_day: float = 0.0,
    https_ok: bool = True,
) -> float:
    """Compute 0-100 quality score from source metrics.

    Uses simplified weights (no NewsGuard, RSF, SSL Labs).
    """
    consumption = CONSUMPTION_SCORES.get(feed_type.lower(), 0)
    consumption_score = min(consumption, 100)

    # Publication frequency: cap at 10 articles/day for 100%
    freq_score = min(articles_per_day / 10.0 * 100, 100) if articles_per_day else 50

    # Feed completeness: already 0-100
    completeness_score = min(max(feed_completeness_pct, 0), 100)

    # HTTPS: 100 or 0
    https_score = 100.0 if https_ok else 0.0

    score = (
        completeness_score * WEIGHTS["feed_completeness"]
        + consumption_score * WEIGHTS["consumption_method"]
        + freq_score * WEIGHTS["publication_frequency"]
        + https_score * WEIGHTS["https"]
    )
    return round(min(max(score, 0), 100), 2)
