"""Article feed and expansion logic. Feed shows clusters, not individual articles."""

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import load_config, load_sources
from app.db import clusters as db_clusters
from app.services import profile_service
from app.services.scoring_service import score_cluster

_IMAGE_SOURCE_SCORES: dict[str, float] = {
    "media_content": 3.0,
    "media_thumbnail": 2.0,
    "enclosure": 2.0,
    "og_image": 1.0,
    "content_html": 1.0,
}
# Fallback for newly incorporated images with unknown or missing image_source
_IMAGE_SOURCE_FALLBACK = 0.5


def select_cluster_image(
    articles: list[dict[str, Any]],
    sources_map: dict[str, dict[str, Any]],
) -> tuple[str | None, str | None]:
    """Select best image URL from cluster articles.

    Returns (image_url, image_source_name). image_source_name is the publisher name
    for legal attribution; None when no image or source unknown.

    Scoring: image_source priority (media_content=3, media_thumbnail=2, enclosure=2,
    og_image=1, content_html=1), then source quality_score as bonus, then earliest
    published_at as tiebreaker. Images with unknown image_source use fallback score
    so newly incorporated images are still displayed.
    """
    candidates: list[tuple[str, str | None, float, datetime | None]] = []
    for art in articles:
        url = art.get("image_url")
        if not url or not isinstance(url, str) or not url.strip():
            continue
        src = art.get("image_source") or ""
        base_score = _IMAGE_SOURCE_SCORES.get(src, _IMAGE_SOURCE_FALLBACK)
        quality = 0.0
        sid = art.get("source_id")
        source_name: str | None = None
        if sid and sources_map:
            src_info = sources_map.get(sid, {})
            source_name = src_info.get("name") or sid
            qs = src_info.get("quality_score")
            if qs is not None:
                try:
                    val = float(qs)
                    quality = val / 100.0 if val > 1 else val
                except (ValueError, TypeError):
                    pass
        total = base_score + quality
        pub = art.get("published_at")
        candidates.append((url, source_name, total, pub))

    if not candidates:
        return (None, None)

    def _sort_key(
        item: tuple[str, str | None, float, datetime | None],
    ) -> tuple[float, float]:
        _url, _sn, score, pub = item
        pub_ts = pub.timestamp() if pub else 0.0
        return (-score, pub_ts)

    candidates.sort(key=_sort_key)
    url, source_name = candidates[0][0], candidates[0][1]
    return (url, source_name)


def _derive_cluster_category(articles: list[dict[str, Any]]) -> str | None:
    """Most common category among cluster articles, or None if none have categories."""
    cats = _derive_cluster_categories(articles)
    return cats[0] if cats else None


def _derive_cluster_categories(articles: list[dict[str, Any]]) -> list[str]:
    """All categories in cluster, ordered by frequency (most common first)."""
    if not articles:
        return []
    counts: Counter[str] = Counter()
    for art in articles:
        cats = art.get("categories")
        if not isinstance(cats, list):
            continue
        for c in cats:
            if c and isinstance(c, str):
                counts[c] += 1
    return [c for c, _ in counts.most_common()]


def _get_rewrite_with_fallback(
    cluster_ids: list[str],
    style: str,
    language: str,
    config: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Get rewrites for cluster_ids. Fall back to default variant if primary missing."""
    rewrites = db_clusters.get_cluster_rewrites(cluster_ids, style, language)
    rewriting = config.get("rewriting", {})
    default_style = rewriting.get("default_style", "neutral")
    default_language = rewriting.get("default_language", "ca")

    missing = [cid for cid in cluster_ids if cid not in rewrites or not rewrites[cid].get("full_text")]
    if missing and (default_style != style or default_language != language):
        fallback = db_clusters.get_cluster_rewrites(missing, default_style, default_language)
        for cid, rw in fallback.items():
            if rw.get("full_text"):
                rewrites[cid] = rw
    return rewrites


def _cluster_matches_topic(
    articles: list[dict[str, Any]],
    topic_id: str,
    sources: dict[str, dict[str, Any]],
) -> bool:
    """True if any article in the cluster matches the given topic (via categories or source)."""
    for art in articles:
        cats = art.get("categories")
        if isinstance(cats, list) and cats and topic_id in {c for c in cats if c}:
            return True
        sid = art.get("source_id")
        if sid:
            src = sources.get(sid, {})
            if topic_id in set(src.get("topics", [])):
                return True
    return False


def get_feed(
    user_id: int,
    topic_filter: str | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """Return today's clusters for the user, filtered by sources/topics.

    If topic_filter is set, only clusters matching that topic are returned.
    Returns (feed, rewrites_pending). rewrites_pending is True when there are
    clusters matching the user's profile but no rewrites yet (e.g. after setup).
    Each feed item has: id (cluster_id), title, summary, full_text, sources (list
    of {source_name, url, title}), relevance_score. Uses cluster_rewrites.
    """
    profile = profile_service.get_profile_with_selections(user_id)
    if not profile:
        return ([], False)
    topic_ids = set(profile.get("topic_ids", []))
    if not topic_ids:
        return ([], False)

    sources = {s["id"]: s for s in load_sources()}
    config = load_config()
    style, language = profile_service.get_reading_variant(profile, config)
    processing = config.get("processing", {})
    window_hours = processing.get("cluster_window_hours", 24)
    limit = processing.get("articles_per_day", 10)

    since: datetime | None = (
        datetime.now(UTC) - timedelta(hours=window_hours)
        if window_hours
        else None
    )
    cluster_rows = db_clusters.get_clusters_with_articles_in_window(since)
    # Filter clusters: keep only if >=1 article matches user's sources and topics
    visible_clusters: list[dict[str, Any]] = []
    for row in cluster_rows:
        cluster_id = row["cluster_id"]
        articles = db_clusters.get_articles_in_cluster(cluster_id)
        for art in articles:
            sid = art["source_id"]
            src = sources.get(sid, {})
            src_topics = set(src.get("topics", []))
            if topic_ids & src_topics:
                visible_clusters.append(
                    {"cluster_id": cluster_id, "articles": articles}
                )
                break

    # Score each cluster
    user_source_ids = set(sources.keys())
    for c in visible_clusters:
        c["relevance_score"] = score_cluster(
            c, user_source_ids, topic_ids, sources, config
        )

    # Partition by source count: multi-source first, singletons as backfill
    min_sources = config.get("relevance", {}).get("min_sources", 2)
    primary: list[dict[str, Any]] = []
    fallback: list[dict[str, Any]] = []
    for c in visible_clusters:
        distinct = len({a["source_id"] for a in c["articles"]})
        if distinct >= min_sources:
            primary.append(c)
        else:
            fallback.append(c)

    primary.sort(key=lambda c: c["relevance_score"], reverse=True)
    fallback.sort(key=lambda c: c["relevance_score"], reverse=True)
    combined = primary + fallback
    visible_clusters = combined[:limit] if limit else combined

    cluster_ids = [c["cluster_id"] for c in visible_clusters]
    rewrites_map = _get_rewrite_with_fallback(cluster_ids, style, language, config)

    result: list[dict[str, Any]] = []
    for cluster_data in visible_clusters:
        cluster_id = cluster_data["cluster_id"]
        articles = cluster_data["articles"]

        if topic_filter and not _cluster_matches_topic(articles, topic_filter, sources):
            continue

        rw = rewrites_map.get(cluster_id)

        # Only show clusters that have an LLM rewrite; never show raw source content
        if not rw or not rw.get("title") or not rw.get("full_text"):
            continue

        sources_list = []
        for art in articles:
            src = sources.get(art["source_id"], {})
            sources_list.append(
                {
                    "source_name": src.get("name", art["source_id"]),
                    "url": art["url"],
                    "title": art.get("title", ""),
                }
            )

        image_url, image_source_name = select_cluster_image(articles, sources)
        categories = _derive_cluster_categories(articles)
        published_at = max(
            (a["published_at"] for a in articles if a.get("published_at")),
            default=None,
        )

        result.append(
            {
                "id": cluster_id,
                "title": rw["title"],
                "summary": rw.get("summary") or "",
                "full_text": rw["full_text"],
                "sources": sources_list,
                "relevance_score": cluster_data.get("relevance_score"),
                "image_url": image_url,
                "image_source_name": image_source_name,
                "categories": categories,
                "published_at": published_at,
            }
        )
    rewrites_pending = len(visible_clusters) > 0 and len(result) == 0
    return (result, rewrites_pending)


def get_expanded_cluster(
    cluster_id: str,
    style: str,
    language: str,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    """Return cluster with full rewritten text and sources for expansion. None if not found."""
    if not db_clusters.cluster_exists(cluster_id):
        return None
    articles = db_clusters.get_articles_in_cluster(cluster_id)
    if not articles:
        return None
    rewrites_map = _get_rewrite_with_fallback([cluster_id], style, language, config)
    rw = rewrites_map.get(cluster_id)
    sources_list = []
    sources_map = {s["id"]: s for s in load_sources()}
    for art in articles:
        src = sources_map.get(art["source_id"], {})
        sources_list.append(
            {
                "source_name": src.get("name", art["source_id"]),
                "url": art["url"],
                "title": art.get("title", ""),
            }
        )

    image_url, image_source_name = select_cluster_image(articles, sources_map)
    categories = _derive_cluster_categories(articles)

    # Never show raw source content; use rewrite or "being prepared" placeholder
    if rw and rw.get("full_text"):
        title = rw.get("title") or "Article"
        summary = rw.get("summary") or ""
        full_text = rw["full_text"]
    else:
        title = "Article"
        summary = ""
        full_text = "This article is being prepared. Please try again shortly."

    return {
        "id": cluster_id,
        "title": title,
        "summary": summary,
        "full_text": full_text,
        "sources": sources_list,
        "image_url": image_url,
        "image_source_name": image_source_name,
        "categories": categories,
    }


