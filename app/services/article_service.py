"""Article feed and expansion logic."""

from datetime import UTC, datetime
from typing import Any

from app.config import load_config, load_sources
from app.db import articles as db_articles
from app.db import rewrites as db_rewrites
from app.services import profile_service


def get_feed(user_id: int) -> list[dict[str, Any]]:
    """Return today's articles for the user, filtered by sources/topics, with summary.

    Each item has: id, title, url, source_id, source_name, published_at, summary,
    full_text (for expand), profile_hash. Falls back to raw_text when no rewrite exists.
    """
    profile = profile_service.get_profile_with_selections(user_id)
    if not profile:
        return []
    source_ids = set(profile.get("source_ids", []))
    topic_ids = set(profile.get("topic_ids", []))
    if not source_ids or not topic_ids:
        return []

    sources = {s["id"]: s for s in load_sources()}
    today_start = datetime.now(UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    config = load_config()
    limit = config.get("processing", {}).get("articles_per_day", 10)

    all_articles = db_articles.get_recent_articles(today_start)
    filtered: list[dict[str, Any]] = []
    for art in all_articles:
        sid = art["source_id"]
        if sid not in source_ids:
            continue
        src = sources.get(sid, {})
        src_topics = set(src.get("topics", []))
        if not (topic_ids & src_topics):
            continue
        filtered.append(art)
        if len(filtered) >= limit:
            break

    profile_hash = profile_service.compute_profile_hash(profile)
    article_ids = [a["id"] for a in filtered]
    rewrites_map = db_rewrites.get_rewrites_for_articles(article_ids, profile_hash)

    result: list[dict[str, Any]] = []
    for art in filtered:
        rw = rewrites_map.get(art["id"])
        summary = (
            rw["summary"] if rw and rw.get("summary") else (art.get("raw_text") or "")
        )
        full_text = (
            rw["full_text"]
            if rw and rw.get("full_text")
            else (art.get("full_text") or art.get("raw_text") or "")
        )
        result.append(
            {
                "id": art["id"],
                "title": art["title"],
                "url": art["url"],
                "source_id": art["source_id"],
                "source_name": sources.get(art["source_id"], {}).get(
                    "name", art["source_id"]
                ),
                "published_at": art.get("published_at"),
                "summary": summary,
                "full_text": full_text,
                "profile_hash": profile_hash,
            }
        )
    return result


def get_expanded_article(article_id: str, profile_hash: str) -> dict[str, Any] | None:
    """Return article with full rewritten text for expansion. None if not found."""
    art = db_articles.get_article_by_id(article_id)
    if not art:
        return None
    rewrites = db_rewrites.get_rewrites_for_articles([article_id], profile_hash)
    rw = rewrites.get(article_id)
    full_text = (
        rw["full_text"]
        if rw and rw.get("full_text")
        else (art.get("full_text") or art.get("raw_text") or "")
    )
    sources = {s["id"]: s for s in load_sources()}
    return {
        "id": art["id"],
        "title": art["title"],
        "url": art["url"],
        "source_id": art["source_id"],
        "source_name": sources.get(art["source_id"], {}).get(
            "name", art["source_id"]
        ),
        "full_text": full_text,
    }
