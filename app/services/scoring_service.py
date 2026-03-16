"""Relevance scoring for news clusters. Computed per cluster per user at feed-build time."""

from datetime import UTC, datetime
from typing import Any


def _recency_score(articles: list[dict[str, Any]], half_life_hours: float) -> float:
    """Exponential decay from max(published_at). 1.0 = just now, ~0.5 at half_life hours."""
    if not articles or half_life_hours <= 0:
        return 0.0
    pubs = [a.get("published_at") for a in articles if a.get("published_at")]
    if not pubs:
        return 0.0
    latest = max(pubs)
    now = datetime.now(UTC)
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=UTC)
    delta = now - latest
    hours_ago = delta.total_seconds() / 3600.0
    if hours_ago <= 0:
        return 1.0
    return 0.5 ** (hours_ago / half_life_hours)


def _coverage_score(articles: list[dict[str, Any]], cap: int) -> float:
    """Distinct sources in cluster, normalized by cap. More sources = bigger story."""
    if not articles or cap <= 0:
        return 0.0
    distinct = len({a.get("source_id") for a in articles if a.get("source_id")})
    return min(distinct / cap, 1.0)


def _topic_affinity_score(
    articles: list[dict[str, Any]],
    user_topic_ids: set[str],
    sources_catalog: dict[str, dict[str, Any]],
) -> float:
    """Fraction of articles whose source topics overlap with user's selected topics."""
    if not articles or not user_topic_ids:
        return 0.0
    matching = 0
    for a in articles:
        sid = a.get("source_id")
        if not sid:
            continue
        src = sources_catalog.get(sid, {})
        src_topics = set(src.get("topics", []))
        if user_topic_ids & src_topics:
            matching += 1
    return matching / len(articles)


def _source_affinity_score(
    articles: list[dict[str, Any]],
    user_source_ids: set[str],
) -> float:
    """Fraction of articles from the user's selected sources."""
    if not articles or not user_source_ids:
        return 0.0
    matching = sum(1 for a in articles if a.get("source_id") in user_source_ids)
    return matching / len(articles)


def _content_quality_score(articles: list[dict[str, Any]]) -> float:
    """Fraction of articles with full_text extracted."""
    if not articles:
        return 0.0
    extracted = sum(
        1 for a in articles if a.get("extraction_status") == "extracted"
    )
    return extracted / len(articles)


def score_cluster(
    cluster_data: dict[str, Any],
    user_source_ids: set[str],
    user_topic_ids: set[str],
    sources_catalog: dict[str, dict[str, Any]],
    config: dict[str, Any],
) -> float:
    """Compute composite relevance score (0.0–1.0) for a cluster.

    Uses weighted combination of recency, coverage, topic affinity,
    source affinity, and content quality.
    """
    articles = cluster_data.get("articles", [])
    if not articles:
        return 0.0

    relevance = config.get("relevance", {})
    weights = relevance.get("weights", {})
    w_recency = weights.get("recency", 0.20)
    w_coverage = weights.get("coverage", 0.35)
    w_topic = weights.get("topic_affinity", 0.20)
    w_source = weights.get("source_affinity", 0.15)
    w_quality = weights.get("content_quality", 0.10)

    half_life = relevance.get("recency_half_life_hours", 8)
    coverage_cap = relevance.get("coverage_cap", 4)

    recency = _recency_score(articles, half_life)
    coverage = _coverage_score(articles, coverage_cap)
    topic_affinity = _topic_affinity_score(articles, user_topic_ids, sources_catalog)
    source_affinity = _source_affinity_score(articles, user_source_ids)
    content_quality = _content_quality_score(articles)

    return (
        w_recency * recency
        + w_coverage * coverage
        + w_topic * topic_affinity
        + w_source * source_affinity
        + w_quality * content_quality
    )
