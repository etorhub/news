"""Orchestrates feed fetching: due-check, fetch, parse, dedup, circuit breaker."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import load_config
from app.db import articles as articles_db
from app.db import sources as sources_db
from app.feed.fetcher import fetch_feed
from app.feed.parser import parse_feed

logger = logging.getLogger(__name__)


@dataclass
class FetchReport:
    """Summary of a fetch run."""

    feeds_checked: int
    feeds_fetched: int
    articles_inserted: int
    feeds_deactivated: int


def _is_feed_due(feed: dict[str, Any], now: datetime) -> bool:
    """Return True if feed should be fetched (due based on poll_interval)."""
    last = feed.get("last_fetched_at")
    interval_min = feed.get("poll_interval_minutes") or 60
    if last is None:
        return True
    if isinstance(last, str):
        try:
            last = datetime.fromisoformat(last.replace("Z", "+00:00"))
        except ValueError:
            return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    due_at = last + timedelta(minutes=interval_min)
    return now >= due_at


def fetch_all_due_feeds(config: dict[str, Any] | None = None) -> FetchReport:
    """Fetch all due feeds, parse, deduplicate, and update metadata.

    Uses config for fetcher settings. Pass config or loads from default path.
    """
    cfg = config or load_config()
    fetcher_cfg = cfg.get("schedule", {}).get("fetcher", {})
    timeout = fetcher_cfg.get("request_timeout_seconds", 30)
    user_agent = fetcher_cfg.get("user_agent", "AccessibleNewsAggregator/0.1")
    threshold = fetcher_cfg.get("circuit_breaker_threshold", 5)

    feeds = sources_db.get_all_active_feeds()
    now = datetime.now(UTC)
    due_feeds = [f for f in feeds if _is_feed_due(f, now)]

    report = FetchReport(
        feeds_checked=len(due_feeds),
        feeds_fetched=0,
        articles_inserted=0,
        feeds_deactivated=0,
    )

    for feed in due_feeds:
        feed_id = feed["id"]
        feed_url = feed["feed_url"]
        source_id = feed["source_id"]

        etag = feed.get("etag")
        last_modified = feed.get("last_modified")

        try:
            result = fetch_feed(
                feed_url,
                etag=etag,
                last_modified=last_modified,
                timeout=float(timeout),
                user_agent=user_agent,
            )
        except Exception as e:
            logger.warning("Fetch failed for %s: %s", feed_url, e)
            failures = (feed.get("consecutive_failures") or 0) + 1
            sources_db.update_feed(feed_id, consecutive_failures=failures)
            if failures >= threshold:
                sources_db.update_feed(feed_id, feed_active=False)
                report.feeds_deactivated += 1
            continue

        if result.is_not_modified:
            sources_db.update_feed(
                feed_id,
                last_fetched_at=now.isoformat(),
            )
            report.feeds_fetched += 1
            continue

        if result.status_code != 200 or result.content is None:
            logger.warning(
                "Feed %s returned %s", feed_url, result.status_code
            )
            failures = (feed.get("consecutive_failures") or 0) + 1
            sources_db.update_feed(feed_id, consecutive_failures=failures)
            if failures >= threshold:
                sources_db.update_feed(feed_id, feed_active=False)
                report.feeds_deactivated += 1
            continue

        try:
            raw_articles = parse_feed(result.content)
        except Exception as e:
            logger.warning("Parse failed for %s: %s", feed_url, e)
            failures = (feed.get("consecutive_failures") or 0) + 1
            sources_db.update_feed(feed_id, consecutive_failures=failures)
            if failures >= threshold:
                sources_db.update_feed(feed_id, feed_active=False)
                report.feeds_deactivated += 1
            continue

        last_guid: str | None = None
        inserted = 0
        for raw in raw_articles:
            article = {
                "source_id": source_id,
                "title": raw["title"],
                "url": raw["url"],
                "published_at": raw.get("published_at"),
                "raw_text": raw.get("raw_text") or "",
                "full_text": raw.get("full_text") or None,
                "guid": raw.get("guid"),
                "image_url": raw.get("image_url"),
                "image_source": raw.get("image_source"),
                "categories": raw.get("categories", []),
            }
            if articles_db.insert_article(article):
                inserted += 1
            last_guid = raw.get("guid") or raw["url"]

        sources_db.update_feed(
            feed_id,
            last_fetched_at=now.isoformat(),
            last_item_guid=last_guid,
            etag=result.etag,
            last_modified=result.last_modified,
            consecutive_failures=0,
        )
        report.feeds_fetched += 1
        report.articles_inserted += inserted

    return report
