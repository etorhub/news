"""LLM rewrite orchestration. Runs on schedule for all (style, language) variants."""

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import load_config

logger = logging.getLogger(__name__)
from app.db import clusters as db_clusters
from app.llm.prompts import load_prompt
from app.llm.provider import LLMProvider, get_provider


@dataclass
class RewriteReport:
    """Summary of a rewrite batch run."""

    variants_processed: int
    clusters_attempted: int
    clusters_succeeded: int
    clusters_failed: int


def _strip_markdown_bold(text: str) -> str:
    """Remove markdown bold markers (**) from the start and end of text."""
    s = text.strip()
    if s.startswith("**"):
        s = s[2:].lstrip()
    if s.endswith("**"):
        s = s[:-2].rstrip()
    return s.strip()


def _parse_cluster_llm_response(text: str) -> tuple[str, str, str]:
    """Parse LLM output into (title, summary, full_text). Raises ValueError on bad format."""
    if not re.search(r"TITLE\s*:", text, re.I):
        raise ValueError("Response missing TITLE:, SUMMARY:, or FULL: sections")
    if not re.search(r"SUMMARY\s*:", text, re.I):
        raise ValueError("Response missing TITLE:, SUMMARY:, or FULL: sections")
    if not re.search(r"FULL\s*:", text, re.I):
        raise ValueError("Response missing TITLE:, SUMMARY:, or FULL: sections")

    parts = re.split(r"FULL\s*:", text, maxsplit=1, flags=re.I)
    if len(parts) != 2:
        raise ValueError("Response missing FULL: section")
    header_part = parts[0]
    full_text = parts[1].strip()

    title = ""
    title_match = re.search(r"TITLE\s*:(.*?)(?=SUMMARY\s*:|$)", header_part, re.I | re.DOTALL)
    if title_match:
        title = title_match.group(1).strip()

    summary = ""
    summary_match = re.search(r"SUMMARY\s*:(.*?)(?=FULL\s*:|$)", header_part, re.I | re.DOTALL)
    if summary_match:
        summary = summary_match.group(1).strip()

    if not title or not summary or not full_text:
        raise ValueError("Empty TITLE, SUMMARY, or FULL section")
    return (
        _strip_markdown_bold(title),
        _strip_markdown_bold(summary),
        _strip_markdown_bold(full_text),
    )


def _build_articles_text(articles: list[dict[str, Any]]) -> str:
    """Build concatenated text of all articles for the prompt."""
    blocks = []
    for i, art in enumerate(articles, 1):
        title = (art.get("title") or "").strip()
        full = (art.get("full_text") or "").strip()
        raw = (art.get("raw_text") or "").strip()
        text = full or raw
        if not text:
            continue
        blocks.append(f"[Source {i}: {title}]\n\n{text}")
    return "\n\n---\n\n".join(blocks) if blocks else ""


def _get_rewriting_variants(config: dict[str, Any]) -> list[tuple[str, str]]:
    """Return list of (style_id, language_id) from config."""
    rewriting = config.get("rewriting", {})
    styles = rewriting.get("styles", [])
    languages = rewriting.get("languages", [])
    if not styles or not languages:
        return [("neutral", "ca")]
    return [
        (s["id"], lang["id"])
        for s in styles
        for lang in languages
    ]


def rewrite_cluster(
    cluster_id: str,
    articles: list[dict[str, Any]],
    style: str,
    language: str,
    config: dict[str, Any],
    *,
    provider: LLMProvider | None = None,
) -> bool:
    """Rewrite a cluster for (style, language) and store. Returns True on success."""
    logger.debug(
        "rewrite_cluster: cluster_id=%s style=%s language=%s articles=%d",
        cluster_id,
        style,
        language,
        len(articles),
    )
    articles_text = _build_articles_text(articles)
    if not articles_text:
        db_clusters.insert_cluster_rewrite(
            cluster_id=cluster_id,
            style=style,
            language=language,
            title=None,
            summary=None,
            full_text=None,
            rewrite_failed=True,
            error_message="Articles have no full_text or raw_text",
        )
        return False

    rewriting = config.get("rewriting", {})
    styles_cfg = {s["id"]: s for s in rewriting.get("styles", [])}
    prompt_name = styles_cfg.get(style, {}).get("prompt", "rewrite_cluster_neutral")
    processing = config.get("processing", {})
    summary_sentences = processing.get("summary_sentences", 3)
    max_tokens = processing.get("rewrite_max_tokens", 2000)

    prompt_template = load_prompt(prompt_name)
    prompt = prompt_template.format(
        articles_text=articles_text,
        language=language,
        summary_sentences=summary_sentences,
    )

    if provider is None:
        provider = get_provider(config)
    try:
        logger.debug(
            "rewrite_cluster: calling LLM cluster_id=%s style=%s language=%s",
            cluster_id,
            style,
            language,
        )
        response = provider.complete(prompt, max_tokens=max_tokens)
        title, summary, full_text = _parse_cluster_llm_response(response)
        db_clusters.insert_cluster_rewrite(
            cluster_id=cluster_id,
            style=style,
            language=language,
            title=title,
            summary=summary,
            full_text=full_text,
            rewrite_failed=False,
        )
        logger.debug("rewrite_cluster: done cluster_id=%s ok=True", cluster_id)
        return True
    except Exception as e:
        err_msg = str(e)[:500]
        db_clusters.insert_cluster_rewrite(
            cluster_id=cluster_id,
            style=style,
            language=language,
            title=None,
            summary=None,
            full_text=None,
            rewrite_failed=True,
            error_message=err_msg,
        )
        logger.debug(
            "rewrite_cluster: done cluster_id=%s ok=False error=%s",
            cluster_id,
            err_msg,
        )
        return False


def _gather_rewrite_work(
    style: str,
    language: str,
    since: datetime | None,
    batch_size: int,
) -> list[tuple[str, list[dict[str, Any]]]]:
    """Return list of (cluster_id, articles) needing rewrite for this (style, language)."""
    clusters = db_clusters.get_clusters_needing_rewrite_for_variant(
        style=style,
        language=language,
        since=since,
        limit=batch_size,
    )
    work: list[tuple[str, list[dict[str, Any]]]] = []
    for row in clusters:
        cluster_id = row["cluster_id"]
        articles = db_clusters.get_articles_in_cluster(cluster_id)
        if articles:
            work.append((cluster_id, articles))
    return work


def _execute_rewrites(
    work: list[tuple[str, list[dict[str, Any]]]],
    style: str,
    language: str,
    config: dict[str, Any],
    provider: LLMProvider,
    parallel_workers: int,
) -> tuple[int, int, int]:
    """Run rewrites for work items. Returns (attempted, succeeded, failed)."""
    total = len(work)
    attempted = 0
    succeeded = 0
    failed = 0
    if parallel_workers > 1:
        with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
            futures = {
                executor.submit(
                    rewrite_cluster,
                    cluster_id,
                    articles,
                    style,
                    language,
                    config,
                    provider=provider,
                ): cluster_id
                for cluster_id, articles in work
            }
            for future in as_completed(futures):
                cluster_id = futures[future]
                attempted += 1
                ok = future.result()
                if ok:
                    succeeded += 1
                else:
                    failed += 1
                short_id = cluster_id[:12]
                status = "ok" if ok else "fail"
                logger.info(
                    "    [%d/%d] %s... %s",
                    attempted,
                    total,
                    short_id,
                    status,
                )
    else:
        for i, (cluster_id, articles) in enumerate(work, 1):
            ok = rewrite_cluster(
                cluster_id=cluster_id,
                articles=articles,
                style=style,
                language=language,
                config=config,
                provider=provider,
            )
            attempted += 1
            if ok:
                succeeded += 1
            else:
                failed += 1
            short_id = cluster_id[:12]
            status = "ok" if ok else "fail"
            logger.info(
                "    [%d/%d] %s... %s",
                i,
                total,
                short_id,
                status,
            )
    return (attempted, succeeded, failed)


def run_rewrite_batch(config: dict[str, Any]) -> RewriteReport:
    """Process clusters for all configured (style, language) variants."""
    logger.info("━━ Rewrite job starting")
    processing = config.get("processing", {})
    window_hours = processing.get("cluster_window_hours", 24)
    since = (
        datetime.now(UTC) - timedelta(hours=window_hours)
        if window_hours
        else None
    )
    schedule_cfg = config.get("schedule", {})
    batch_size = schedule_cfg.get("rewrite_batch_size", 10)
    parallel_workers = schedule_cfg.get("rewrite_parallel_workers", 1)

    variants = _get_rewriting_variants(config)
    variant_str = ", ".join(f"{s}/{l}" for s, l in variants)
    logger.info(
        "  Variants: %s (batch_size=%d, workers=%d)",
        variant_str or "none",
        batch_size,
        parallel_workers,
    )

    clusters_attempted = 0
    clusters_succeeded = 0
    clusters_failed = 0
    provider: LLMProvider | None = None

    for style, language in variants:
        work = _gather_rewrite_work(style, language, since, batch_size)
        if not work:
            logger.info("  [%s/%s] No clusters needing rewrite", style, language)
            continue

        logger.info(
            "  [%s/%s] Rewriting %d cluster(s)...",
            style,
            language,
            len(work),
        )

        if provider is None:
            logger.info("  Loading LLM provider...")
            provider = get_provider(config)

        a, s, f = _execute_rewrites(
            work, style, language, config, provider, parallel_workers
        )
        clusters_attempted += a
        clusters_succeeded += s
        clusters_failed += f
        logger.info(
            "  [%s/%s] Done: %d attempted, %d ok, %d failed",
            style,
            language,
            a,
            s,
            f,
        )

    logger.info(
        "━━ Rewrite complete: %d attempted, %d ok, %d failed",
        clusters_attempted,
        clusters_succeeded,
        clusters_failed,
    )
    return RewriteReport(
        variants_processed=len(variants),
        clusters_attempted=clusters_attempted,
        clusters_succeeded=clusters_succeeded,
        clusters_failed=clusters_failed,
    )


