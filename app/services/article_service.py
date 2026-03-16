"""Article feed and expansion logic. Feed shows clusters, not individual articles."""

from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import load_config, load_sources
from app.db import clusters as db_clusters
from app.services import profile_service


def get_feed(user_id: int) -> list[dict[str, Any]]:
    """Return today's clusters for the user, filtered by sources/topics.

    Each item has: id (cluster_id), title, summary, full_text, sources (list of
    {source_name, url, title}), profile_hash. Uses cluster_rewrites.
    """
    # #region agent log
    import json
    import os
    _log_path = "/home/etor/code/news/.cursor/debug-72c858.log"
    def _dbg(msg: str, data: dict) -> None:
        os.makedirs(os.path.dirname(_log_path), exist_ok=True)
        with open(_log_path, "a") as f:
            f.write(json.dumps({"sessionId": "72c858", "location": "article_service.py:get_feed", "message": msg, "data": data, "timestamp": __import__("time").time_ns() // 1_000_000}) + "\n")
    # #endregion
    profile = profile_service.get_profile_with_selections(user_id)
    if not profile:
        _dbg("early_exit", {"hypothesisId": "A", "reason": "no_profile", "user_id": user_id})
        return []
    source_ids = set(profile.get("source_ids", []))
    topic_ids = set(profile.get("topic_ids", []))
    if not source_ids or not topic_ids:
        _dbg("early_exit", {"hypothesisId": "A", "reason": "empty_sources_or_topics", "user_id": user_id, "source_ids": list(source_ids), "topic_ids": list(topic_ids)})
        return []

    sources = {s["id"]: s for s in load_sources()}
    config = load_config()
    processing = config.get("processing", {})
    window_hours = processing.get("cluster_window_hours", 24)
    limit = processing.get("articles_per_day", 10)

    since = datetime.now(UTC) - timedelta(hours=window_hours)
    cluster_rows = db_clusters.get_clusters_with_articles_in_window(since)
    _dbg("clusters_in_window", {"hypothesisId": "B", "user_id": user_id, "cluster_count": len(cluster_rows), "window_hours": window_hours})

    # Filter clusters: keep only if >=1 article matches user's sources and topics
    visible_clusters: list[dict[str, Any]] = []
    for row in cluster_rows:
        cluster_id = row["cluster_id"]
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

    # Sort by most recent article in cluster, limit
    def _latest_pub(cluster_data: dict) -> datetime | None:
        arts = cluster_data.get("articles", [])
        if not arts:
            return None
        pubs = [a.get("published_at") for a in arts if a.get("published_at")]
        return max(pubs) if pubs else None

    visible_clusters.sort(
        key=lambda c: _latest_pub(c) or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    visible_clusters = visible_clusters[:limit]
    _dbg("visible_clusters_after_filter", {"hypothesisId": "C", "user_id": user_id, "visible_count": len(visible_clusters), "source_ids": list(source_ids), "topic_ids": list(topic_ids)})

    profile_hash = profile_service.compute_profile_hash(profile)
    cluster_ids = [c["cluster_id"] for c in visible_clusters]
    rewrites_map = db_clusters.get_cluster_rewrites(cluster_ids, profile_hash)
    _dbg("rewrites_lookup", {"hypothesisId": "D", "user_id": user_id, "profile_hash": profile_hash, "cluster_ids_requested": len(cluster_ids), "rewrites_found": len(rewrites_map), "rewrite_keys": list(rewrites_map.keys())})

    result: list[dict[str, Any]] = []
    for cluster_data in visible_clusters:
        cluster_id = cluster_data["cluster_id"]
        articles = cluster_data["articles"]
        rw = rewrites_map.get(cluster_id)

        # Only show clusters that have an LLM rewrite; never show raw source content
        if not rw or not rw.get("title") or not rw.get("full_text"):
            _dbg("cluster_skipped_no_rewrite", {"hypothesisId": "E", "cluster_id": cluster_id, "has_rw": rw is not None, "has_title": bool(rw.get("title") if rw else False), "has_full_text": bool(rw.get("full_text") if rw else False)})
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

        result.append(
            {
                "id": cluster_id,
                "title": rw["title"],
                "summary": rw.get("summary") or "",
                "full_text": rw["full_text"],
                "sources": sources_list,
                "profile_hash": profile_hash,
            }
        )
    _dbg("feed_result", {"hypothesisId": "all", "user_id": user_id, "result_count": len(result)})
    return result


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
    }
