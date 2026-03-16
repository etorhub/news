"""Thin wrapper around trafilatura for article body extraction."""

import logging

import trafilatura

logger = logging.getLogger(__name__)


def extract_article(url: str, timeout: int = 30) -> str | None:
    """Fetch URL and extract main article body as plain text.

    Returns extracted text or None on network error, extraction failure,
    or empty result.
    """
    try:
        downloaded = trafilatura.fetch_url(url)
    except Exception as e:
        logger.warning("trafilatura fetch failed for %s: %s", url, e)
        return None

    if not downloaded:
        logger.debug("trafilatura fetch returned empty for %s", url)
        return None

    try:
        result = trafilatura.extract(
            downloaded,
            output_format="txt",
            include_comments=False,
        )
    except Exception as e:
        logger.warning("trafilatura extract failed for %s: %s", url, e)
        return None

    if not result or not result.strip():
        logger.debug("trafilatura extract returned empty for %s", url)
        return None

    return result.strip()
