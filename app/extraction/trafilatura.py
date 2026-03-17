"""Thin wrapper around trafilatura for article body extraction."""

import re
import logging

import trafilatura

logger = logging.getLogger(__name__)

_OG_IMAGE_RE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
_OG_IMAGE_RE_ALT = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    re.I,
)


def _extract_og_image(html: str) -> str | None:
    """Extract og:image URL from HTML. Returns None if not found."""
    for pattern in (_OG_IMAGE_RE, _OG_IMAGE_RE_ALT):
        match = pattern.search(html)
        if match:
            url = match.group(1).strip()
            if url.startswith(("http://", "https://")):
                return url
    return None


def extract_article(url: str, timeout: int = 30) -> tuple[str | None, str | None]:
    """Fetch URL and extract main article body as plain text.

    Returns (extracted_text, og_image_url). Either can be None on failure.
    og_image_url is extracted from the page HTML before text extraction.
    """
    try:
        downloaded = trafilatura.fetch_url(url)
    except Exception as e:
        logger.warning("trafilatura fetch failed for %s: %s", url, e)
        return (None, None)

    if not downloaded:
        logger.debug("trafilatura fetch returned empty for %s", url)
        return (None, None)

    og_image_url = _extract_og_image(downloaded)

    try:
        result = trafilatura.extract(
            downloaded,
            output_format="txt",
            include_comments=False,
        )
    except Exception as e:
        logger.warning("trafilatura extract failed for %s: %s", url, e)
        return (None, og_image_url)

    if not result or not result.strip():
        logger.debug("trafilatura extract returned empty for %s", url)
        return (None, og_image_url)

    return (result.strip(), og_image_url)
