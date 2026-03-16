"""Feed detection and validation for news sources."""

import re
from urllib.parse import urljoin, urlparse

import feedparser
import httpx

FEED_PATH_CANDIDATES = [
    "/feed",
    "/feed/",
    "/rss",
    "/rss/",
    "/rss.xml",
    "/feed.xml",
    "/atom.xml",
    "/feeds/posts/default",
    "/?feed=rss2",
    "/news/rss.xml",
    "/en/rss.xml",
    "/sitemap_news.xml",
]

# Content types that indicate RSS/Atom
FEED_CONTENT_TYPES = (
    "application/rss+xml",
    "application/atom+xml",
    "application/xml",
    "text/xml",
)


def _is_feed_content_type(content_type: str) -> bool:
    """Check if Content-Type indicates a feed."""
    if not content_type:
        return False
    ct = content_type.split(";")[0].strip().lower()
    return any(ct.startswith(t) for t in FEED_CONTENT_TYPES)


def _extract_base_url(url: str) -> str:
    """Extract scheme + netloc from URL."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _parse_link_tags(html: str, base_url: str) -> list[dict[str, str]]:
    """Extract feed URLs from HTML link rel='alternate' tags."""
    feeds: list[dict[str, str]] = []
    # Match <link rel="alternate" type="application/rss+xml" href="...">
    pattern = re.compile(
        r'<link[^>]+rel=["\']alternate["\'][^>]+href=["\']([^"\']+)["\'][^>]*(?:type=["\']([^"\']+)["\'])?[^>]*>',
        re.IGNORECASE,
    )
    for m in pattern.finditer(html):
        href = m.group(1).strip()
        link_type = m.group(2) or ""
        lt = link_type.lower()
        if "rss" in lt or "atom" in lt or "xml" in link_type:
            full_url = urljoin(base_url, href)
            ftype = "rss" if "rss" in lt else "atom"
            feeds.append({"url": full_url, "type": ftype})
    # Also match href first: <link href="..." rel="alternate" type="...">
    pattern2 = re.compile(
        r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']alternate["\'][^>]+type=["\']([^"\']+)["\'][^>]*>',
        re.IGNORECASE,
    )
    for m in pattern2.finditer(html):
        href = m.group(1).strip()
        link_type = m.group(2) or ""
        lt = link_type.lower()
        if "rss" in lt or "atom" in lt:
            full_url = urljoin(base_url, href)
            ftype = "rss" if "rss" in lt else "atom"
            feeds.append({"url": full_url, "type": ftype})
    return feeds


def detect_feeds(homepage_url: str) -> list[dict[str, str]]:
    """Discover RSS/Atom feeds for a source by trying standard paths and parsing HTML.

    Returns a list of dicts with keys: url, type (rss|atom), label (optional).
    """
    base = _extract_base_url(homepage_url)
    found: list[dict[str, str]] = []
    seen: set[str] = set()

    def add_feed(url: str, feed_type: str, label: str | None = None) -> None:
        if url not in seen:
            seen.add(url)
            found.append({"url": url, "type": feed_type, "label": label or "main"})

    # 1. Try standard feed paths
    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        for path in FEED_PATH_CANDIDATES:
            try:
                url = urljoin(base, path)
                resp = client.get(url)
                if resp.status_code == 200 and _is_feed_content_type(
                    resp.headers.get("Content-Type", "")
                ):
                    add_feed(url, "rss", "main")
                    break  # One working feed from paths is enough
            except Exception:
                continue

        # 2. Parse homepage for link rel="alternate"
        try:
            resp = client.get(homepage_url)
            if resp.status_code == 200:
                for feed in _parse_link_tags(resp.text, homepage_url):
                    add_feed(feed["url"], feed["type"], None)
        except Exception:
            pass

    return found


def validate_feed(feed_url: str) -> dict[str, str | int | float | None]:
    """Fetch and parse a feed, return validation result.

    Returns dict with: ok (bool), item_count (int), completeness_pct (float),
    feed_type (str), error (str | None).
    """
    result: dict[str, str | int | float | None] = {
        "ok": False,
        "item_count": 0,
        "completeness_pct": 0.0,
        "feed_type": "unknown",
        "error": None,
    }
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(feed_url)
            if resp.status_code != 200:
                result["error"] = f"HTTP {resp.status_code}"
                return result

            parsed = feedparser.parse(resp.text)
            if parsed.bozo and not parsed.entries:
                result["error"] = "Parse error: invalid or empty feed"
                return result

            entries = parsed.entries or []
            result["item_count"] = len(entries)

            # Determine feed type from parsed structure
            if hasattr(parsed, "version") and parsed.version:
                v = str(parsed.version).lower()
                if "rss" in v:
                    result["feed_type"] = "rss"
                elif "atom" in v:
                    result["feed_type"] = "atom"
                else:
                    result["feed_type"] = "rss"  # Default

            # Completeness: % items with title + (desc or content) + link + date
            if not entries:
                result["ok"] = True
                result["completeness_pct"] = 100.0
                return result

            complete = 0
            for entry in entries:
                has_title = bool(entry.get("title"))
                has_link = bool(entry.get("link"))
                has_content = bool(entry.get("summary") or entry.get("description"))
                if entry.get("content"):
                    has_content = True
                has_date = bool(entry.get("published") or entry.get("updated"))
                if has_title and has_link and (has_content or has_date):
                    complete += 1

            result["completeness_pct"] = round(100.0 * complete / len(entries), 1)
            result["ok"] = True
            return result

    except httpx.TimeoutException:
        result["error"] = "Timeout"
        return result
    except Exception as e:
        result["error"] = str(e)
        return result
