"""Article feed and expansion logic. Feed shows clusters, not individual articles."""

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import load_config, load_sources
from app.db import clusters as db_clusters
from app.services import profile_service
from app.services.scoring_service import score_cluster

_IMAGE_SOURCE_SCORES: dict[str, int] = {
    "media_content": 3,
    "media_thumbnail": 2,
    "enclosure": 2,
    "og_image": 1,
    "content_html": 1,
}


def select_cluster_image(
    articles: list[dict[str, Any]],
    sources_map: dict[str, dict[str, Any]],
) -> str | None:
    """Select best image URL from cluster articles.

    Scoring: image_source priority (media_content=3, media_thumbnail=2, enclosure=2,
    og_image=1, content_html=1), then source quality_score as bonus, then earliest
    published_at as tiebreaker.
    """
    candidates: list[tuple[str, float, datetime | None]] = []
    for art in articles:
        url = art.get("image_url")
        if not url:
            continue
        src = art.get("image_source") or ""
        base_score = _IMAGE_SOURCE_SCORES.get(src, 0)
        if base_score == 0:
            continue
        quality = 0.0
        sid = art.get("source_id")
        if sid and sources_map:
            src_info = sources_map.get(sid, {})
            qs = src_info.get("quality_score")
            if qs is not None:
                try:
                    val = float(qs)
                    quality = val / 100.0 if val > 1 else val
                except (ValueError, TypeError):
                    pass
        total = base_score + quality
        pub = art.get("published_at")
        candidates.append((url, total, pub))

    if not candidates:
        return None

    def _sort_key(item: tuple[str, float, datetime | None]) -> tuple[float, float]:
        url, score, pub = item
        pub_ts = pub.timestamp() if pub else 0.0
        return (-score, pub_ts)

    candidates.sort(key=_sort_key)
    return candidates[0][0]


def _derive_cluster_category(articles: list[dict[str, Any]]) -> str | None:
    """Most common category among cluster articles, or None if none have categories."""
    if not articles:
        return None
    counts: Counter[str] = Counter()
    for art in articles:
        cats = art.get("categories")
        if not isinstance(cats, list):
            continue
        for c in cats:
            if c and isinstance(c, str):
                counts[c] += 1
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def get_feed(user_id: int) -> tuple[list[dict[str, Any]], bool]:
    """Return today's clusters for the user, filtered by sources/topics.

    Returns (feed, rewrites_pending). rewrites_pending is True when there are
    clusters matching the user's profile but no rewrites yet (e.g. after setup).
    Each feed item has: id (cluster_id), title, summary, full_text, sources (list
    of {source_name, url, title}), profile_hash, relevance_score. Uses cluster_rewrites.
    """
    profile = profile_service.get_profile_with_selections(user_id)
    if not profile:
        return ([], False)
    source_ids = set(profile.get("source_ids", []))
    topic_ids = set(profile.get("topic_ids", []))
    if not source_ids or not topic_ids:
        return ([], False)

    sources = {s["id"]: s for s in load_sources()}
    config = load_config()
    processing = config.get("processing", {})
    window_hours = processing.get("cluster_window_hours", 24)
    limit = processing.get("articles_per_day", 10)

    since: datetime | None = (
        datetime.now(UTC) - timedelta(hours=window_hours)
        if window_hours
        else None
    )
    cluster_rows = db_clusters.get_clusters_with_articles_in_window(since)
    read_ids = db_clusters.get_read_cluster_ids(user_id)

    # Filter clusters: keep only if >=1 article matches user's sources and topics
    # Exclude clusters the user has marked as read
    visible_clusters: list[dict[str, Any]] = []
    for row in cluster_rows:
        cluster_id = row["cluster_id"]
        if cluster_id in read_ids:
            continue
        articles = db_clusters.get_articles_in_cluster(cluster_id)
        for art in articles:
            sid = art["source_id"]
            if sid not in source_ids:
                continue
            src = sources.get(sid, {})
            src_topics = set(src.get("topics", []))
            if topic_ids & src_topics:
                visible_clusters.append(
                    {"cluster_id": cluster_id, "articles": articles}
                )
                break

    # Score each cluster
    for c in visible_clusters:
        c["relevance_score"] = score_cluster(
            c, source_ids, topic_ids, sources, config
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

    profile_hash = profile_service.compute_profile_hash(profile)
    cluster_ids = [c["cluster_id"] for c in visible_clusters]
    rewrites_map = db_clusters.get_cluster_rewrites(cluster_ids, profile_hash)

    result: list[dict[str, Any]] = []
    for cluster_data in visible_clusters:
        cluster_id = cluster_data["cluster_id"]
        articles = cluster_data["articles"]
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

        image_url = select_cluster_image(articles, sources)
        category = _derive_cluster_category(articles)

        result.append(
            {
                "id": cluster_id,
                "title": rw["title"],
                "summary": rw.get("summary") or "",
                "full_text": rw["full_text"],
                "sources": sources_list,
                "profile_hash": profile_hash,
                "relevance_score": cluster_data.get("relevance_score"),
                "image_url": image_url,
                "category": category,
            }
        )
    rewrites_pending = len(visible_clusters) > 0 and len(result) == 0
    return (result, rewrites_pending)


def get_expanded_cluster(cluster_id: str, profile_hash: str) -> dict[str, Any] | None:
    """Return cluster with full rewritten text and sources for expansion. None if not found."""
    if not db_clusters.cluster_exists(cluster_id):
        return None
    articles = db_clusters.get_articles_in_cluster(cluster_id)
    if not articles:
        return None
    rewrites = db_clusters.get_cluster_rewrites([cluster_id], profile_hash)
    rw = rewrites.get(cluster_id)
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

    image_url = select_cluster_image(articles, sources_map)
    category = _derive_cluster_category(articles)

    # Never show raw source content; use rewrite or "being prepared" placeholder
    if rw and rw.get("full_text"):
        title = rw.get("title") or "Article"
        full_text = rw["full_text"]
    else:
        title = "Article"
        full_text = "This article is being prepared. Please try again shortly."

    return {
        "id": cluster_id,
        "title": title,
        "full_text": full_text,
        "sources": sources_list,
        "image_url": image_url,
        "category": category,
    }


def mark_cluster_read(user_id: int, cluster_id: str) -> None:
    """Mark a cluster as read for a user."""
    db_clusters.mark_cluster_read(user_id, cluster_id)


def get_read_feed(user_id: int) -> list[dict[str, Any]]:
    """Return read clusters for the archive, ordered by read_at DESC.

    Each item has: id, title, summary, full_text, sources, read_at.
    """
    profile = profile_service.get_profile_with_selections(user_id)
    if not profile:
        return []
    profile_hash = profile_service.compute_profile_hash(profile)
    sources = {s["id"]: s for s in load_sources()}

    rows = db_clusters.get_read_clusters_with_rewrites(
        user_id, profile_hash, limit=50, offset=0
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        cluster_id = row["cluster_id"]
        articles = db_clusters.get_articles_in_cluster(cluster_id)
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
        image_url = select_cluster_image(articles, sources)
        category = _derive_cluster_category(articles)
        result.append(
            {
                "id": cluster_id,
                "title": row["title"] or "",
                "summary": row.get("summary") or "",
                "full_text": row.get("full_text") or "",
                "sources": sources_list,
                "read_at": row["read_at"],
                "image_url": image_url,
                "category": category,
            }
        )
    return result
