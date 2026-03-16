"""RSS/Atom feed parser and normalizer."""

import re
from datetime import UTC, datetime
from html import unescape
from typing import Any, TypedDict

import feedparser
from feedparser import FeedParserDict


class RawArticle(TypedDict):
    """Normalized article from a feed entry."""

    guid: str
    title: str
    url: str
    published_at: datetime | None
    raw_text: str
    full_text: str


def _strip_html(html: str) -> str:
    """Remove HTML tags and decode entities. Simple implementation."""
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    return unescape(text).strip()


def _parse_date(entry: FeedParserDict) -> datetime | None:
    """Extract published/updated date from entry."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime(
            parsed[0], parsed[1], parsed[2], parsed[3], parsed[4], parsed[5],
            tzinfo=UTC,
        )
    return None


def _get_guid(entry: FeedParserDict) -> str:
    """Extract guid or fall back to link."""
    guid = entry.get("guid") or entry.get("id")
    if isinstance(guid, str):
        return guid
    if hasattr(guid, "get") and isinstance(guid, dict):
        return str(guid.get("guid", "") or entry.get("link", ""))
    return str(entry.get("link", ""))


def _get_url(entry: FeedParserDict) -> str:
    """Extract canonical URL from entry."""
    link = entry.get("link")
    if link:
        return str(link)
    guid = entry.get("guid") or entry.get("id")
    if isinstance(guid, str) and guid.startswith(("http://", "https://")):
        return guid
    return ""


def _get_raw_text(entry: FeedParserDict) -> str:
    """Extract summary/description as raw text."""
    summary = entry.get("summary") or entry.get("description")
    if not summary:
        return ""
    if isinstance(summary, str):
        return _strip_html(summary)
    if hasattr(summary, "get") and isinstance(summary, dict):
        return _strip_html(str(summary.get("value", "")))
    return ""


def _get_full_text(entry: FeedParserDict) -> str:
    """Extract full content from content:encoded or content block."""
    content = entry.get("content")
    if not content or not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and "value" in block:
            val = block["value"]
            if isinstance(val, str):
                parts.append(_strip_html(val))
    return "\n\n".join(parts) if parts else ""


def parse_feed(content: bytes) -> list[dict[str, Any]]:
    """Parse RSS/Atom feed content into normalized RawArticle dicts.

    Each dict has: guid, title, url, published_at, raw_text, full_text.
    """
    parsed = feedparser.parse(content)
    entries = parsed.get("entries", [])
    result: list[dict[str, Any]] = []

    for entry in entries:
        url = _get_url(entry)
        if not url:
            continue

        title = entry.get("title") or "(No title)"
        if not isinstance(title, str):
            title = str(title)

        result.append(
            {
                "guid": _get_guid(entry),
                "title": title,
                "url": url,
                "published_at": _parse_date(entry),
                "raw_text": _get_raw_text(entry),
                "full_text": _get_full_text(entry),
            }
        )

    return result
