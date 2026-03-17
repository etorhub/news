"""Batch enrichment orchestrator for article content extraction."""

import logging
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from app.db import articles as db_articles
from app.extraction.trafilatura import extract_article

logger = logging.getLogger(__name__)


@dataclass
class EnrichmentReport:
    """Summary of an enrichment run."""

    articles_checked: int
    articles_extracted: int
    articles_failed: int
    articles_skipped: int


def _domain_from_url(url: str) -> str:
    """Extract domain from URL for rate limiting."""
    try:
        parsed = urlparse(url)
        return parsed.netloc or url
    except Exception:
        return url


def enrich_articles(config: dict) -> EnrichmentReport:
    """Process articles needing extraction. Returns EnrichmentReport."""
    extraction_cfg = config.get("extraction", {})
    if not extraction_cfg.get("enabled", True):
        return EnrichmentReport(0, 0, 0, 0)

    batch_size = extraction_cfg.get("batch_size", 30)
    min_content_length = extraction_cfg.get("min_content_length", 200)
    rate_limit = extraction_cfg.get("rate_limit_per_domain", 2.0)
    timeout = extraction_cfg.get("timeout", 30)

    candidates = db_articles.get_articles_needing_extraction(limit=batch_size)
    if not candidates:
        return EnrichmentReport(0, 0, 0, 0)

    # Group by domain for rate limiting
    by_domain: dict[str, list[dict]] = {}
    for art in candidates:
        domain = _domain_from_url(art["url"])
        by_domain.setdefault(domain, []).append(art)

    report = EnrichmentReport(
        articles_checked=0,
        articles_extracted=0,
        articles_failed=0,
        articles_skipped=0,
    )

    min_interval = 1.0 / rate_limit if rate_limit > 0 else 0

    for _domain, arts in by_domain.items():
        for art in arts:
            report.articles_checked += 1
            article_id = art["id"]
            url = art["url"]
            full_text = art.get("full_text") or ""
            raw_text = art.get("raw_text") or ""

            # Skip if RSS already provided enough content
            if len(full_text) >= min_content_length:
                db_articles.update_article_extraction(
                    article_id, full_text, "skipped", "rss"
                )
                report.articles_skipped += 1
                continue

            # Extract with trafilatura
            extracted, og_image_url = extract_article(url, timeout=timeout)

            # Use og:image as fallback only if article has no image from RSS
            image_url: str | None = None
            image_source: str | None = None
            if not art.get("image_url") and og_image_url:
                image_url = og_image_url
                image_source = "og_image"

            if extracted and len(extracted) >= min_content_length:
                db_articles.update_article_extraction(
                    article_id,
                    extracted,
                    "extracted",
                    "trafilatura",
                    image_url=image_url,
                    image_source=image_source,
                )
                report.articles_extracted += 1
            else:
                # Keep raw_text as fallback, mark failed
                fallback = full_text or raw_text
                db_articles.update_article_extraction(
                    article_id,
                    fallback or None,
                    "failed",
                    "trafilatura",
                    image_url=image_url,
                    image_source=image_source,
                )
                report.articles_failed += 1
                logger.debug(
                    "Extraction failed or insufficient for %s (got %d chars)",
                    url,
                    len(extracted or ""),
                )

            time.sleep(min_interval)

    return report


def enrich_all_articles(config: dict) -> EnrichmentReport:
    """Process all pending articles in batches until none remain or max rounds hit.

    Returns aggregate EnrichmentReport. Used by scheduler so clustering never
    runs with pending extraction.
    """
    extraction_cfg = config.get("extraction", {})
    if not extraction_cfg.get("enabled", True):
        return EnrichmentReport(0, 0, 0, 0)

    max_rounds = extraction_cfg.get("max_enrichment_rounds", 20)
    aggregate = EnrichmentReport(0, 0, 0, 0)

    for round_num in range(max_rounds):
        pending = db_articles.get_pending_extraction_count()
        if pending == 0:
            break

        report = enrich_articles(config)
        aggregate.articles_checked += report.articles_checked
        aggregate.articles_extracted += report.articles_extracted
        aggregate.articles_failed += report.articles_failed
        aggregate.articles_skipped += report.articles_skipped

        if report.articles_checked == 0:
            break

        remaining = db_articles.get_pending_extraction_count()
        if remaining > 0:
            logger.info(
                "Enrichment round %d: %d processed, %d pending remaining",
                round_num + 1,
                report.articles_checked,
                remaining,
            )

    return aggregate
