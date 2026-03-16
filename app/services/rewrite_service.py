"""LLM rewrite orchestration. Runs on schedule or via manual trigger after settings save."""

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import load_config

logger = logging.getLogger(__name__)
from app.db import clusters as db_clusters
from app.db import users as db_users
from app.llm.prompts import load_prompt
from app.llm.provider import LLMProvider, get_provider
from app.services import profile_service


@dataclass
class RewriteReport:
    """Summary of a rewrite batch run."""

    profiles_processed: int
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
    # Case-insensitive markers (small models may output "Title:" or "Título:" etc.)
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


def rewrite_cluster(
    cluster_id: str,
    articles: list[dict[str, Any]],
    profile: dict[str, Any],
    config: dict[str, Any],
    *,
    provider: LLMProvider | None = None,
) -> bool:
    """Rewrite a cluster (merge + adapt all articles) and store. Returns True on success."""
    logger.info("rewrite_cluster: starting cluster_id=%s articles=%d", cluster_id, len(articles))
    articles_text = _build_articles_text(articles)
    if not articles_text:
        profile_hash = profile_service.compute_profile_hash(profile)
        db_clusters.insert_cluster_rewrite(
            cluster_id=cluster_id,
            profile_hash=profile_hash,
            title=None,
            summary=None,
            full_text=None,
            rewrite_failed=True,
            error_message="Articles have no full_text or raw_text",
        )
        return False

    profile_hash = profile_service.compute_profile_hash(profile)
    processing = config.get("processing", {})
    summary_sentences = processing.get("summary_sentences", 3)
    max_tokens = processing.get("rewrite_max_tokens", 2000)
    language = (profile.get("language") or "ca").strip() or "ca"
    prompt_template = load_prompt("rewrite_cluster")
    prompt = prompt_template.format(
        articles_text=articles_text,
        language=language,
        rewrite_tone=profile.get(
            "rewrite_tone",
            "Short sentences. Simple vocabulary. No jargon.",
        ),
        filter_negative=str(profile.get("filter_negative", False)).lower(),
        summary_sentences=summary_sentences,
    )

    if provider is None:
        provider = get_provider(config)
    try:
        logger.info("rewrite_cluster: calling LLM cluster_id=%s max_tokens=%d", cluster_id, max_tokens)
        response = provider.complete(prompt, max_tokens=max_tokens)
        title, summary, full_text = _parse_cluster_llm_response(response)
        db_clusters.insert_cluster_rewrite(
            cluster_id=cluster_id,
            profile_hash=profile_hash,
            title=title,
            summary=summary,
            full_text=full_text,
            rewrite_failed=False,
        )
        logger.info("rewrite_cluster: done cluster_id=%s ok=True", cluster_id)
        return True
    except Exception as e:
        err_msg = str(e)[:500]
        db_clusters.insert_cluster_rewrite(
            cluster_id=cluster_id,
            profile_hash=profile_hash,
            title=None,
            summary=None,
            full_text=None,
            rewrite_failed=True,
            error_message=err_msg,
        )
        logger.warning("rewrite_cluster: done cluster_id=%s ok=False error=%s", cluster_id, err_msg)
        return False


def _rewrite_one(
    cluster_id: str,
    articles: list[dict[str, Any]],
    profile: dict[str, Any],
    config: dict[str, Any],
    provider: LLMProvider | None,
) -> bool:
    """Single-cluster rewrite for use in parallel executor."""
    return rewrite_cluster(
        cluster_id=cluster_id,
        articles=articles,
        profile=profile,
        config=config,
        provider=provider,
    )


def run_rewrite_batch(config: dict[str, Any]) -> RewriteReport:
    """Process today's clusters for all distinct rewrite profiles."""
    logger.info("run_rewrite_batch: starting")
    processing = config.get("processing", {})
    window_hours = processing.get("cluster_window_hours", 24)
    since = datetime.now(UTC) - timedelta(hours=window_hours)
    schedule_cfg = config.get("schedule", {})
    batch_size = schedule_cfg.get("rewrite_batch_size", 10)
    parallel_workers = schedule_cfg.get("rewrite_parallel_workers", 2)
    logger.info(
        "run_rewrite_batch: window_hours=%d batch_size=%d parallel_workers=%d",
        window_hours,
        batch_size,
        parallel_workers,
    )

    profiles = db_users.get_distinct_rewrite_profiles()
    logger.info("run_rewrite_batch: got profiles=%d", len(profiles))
    clusters_attempted = 0
    clusters_succeeded = 0
    clusters_failed = 0
    provider: LLMProvider | None = None

    for profile in profiles:
        profile_hash = profile_service.compute_profile_hash(profile)
        clusters = db_clusters.get_clusters_needing_rewrite(
            profile_hash=profile_hash,
            since=since,
            limit=batch_size,
        )
        logger.info(
            "run_rewrite_batch: profile_hash=%s clusters_needing_rewrite=%d",
            profile_hash[:12] if profile_hash else "none",
            len(clusters),
        )
        work: list[tuple[str, list[dict[str, Any]]]] = []
        for row in clusters:
            cluster_id = row["cluster_id"]
            articles = db_clusters.get_articles_in_cluster(cluster_id)
            if articles:
                work.append((cluster_id, articles))

        if not work:
            continue

        # Share provider across calls. Eager-load in main thread to avoid
        # deadlock when workers load concurrently (local LLM).
        if provider is None:
            logger.info("run_rewrite_batch: loading provider")
            provider = get_provider(config)
            logger.info("run_rewrite_batch: provider ready, processing %d clusters", len(work))

        if parallel_workers > 1:
            with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
                futures = {
                    executor.submit(
                        _rewrite_one,
                        cluster_id,
                        articles,
                        profile,
                        config,
                        provider,
                    ): cluster_id
                    for cluster_id, articles in work
                }
                for future in as_completed(futures):
                    clusters_attempted += 1
                    if future.result():
                        clusters_succeeded += 1
                    else:
                        clusters_failed += 1
                logger.info(
                    "run_rewrite_batch: profile done attempted=%d ok=%d failed=%d",
                    len(work),
                    clusters_succeeded,
                    clusters_failed,
                )
        else:
            for cluster_id, articles in work:
                clusters_attempted += 1
                if rewrite_cluster(
                    cluster_id=cluster_id,
                    articles=articles,
                    profile=profile,
                    config=config,
                    provider=provider,
                ):
                    clusters_succeeded += 1
                else:
                    clusters_failed += 1
            logger.info(
                "run_rewrite_batch: profile done attempted=%d ok=%d failed=%d",
                len(work),
                clusters_succeeded,
                clusters_failed,
            )

    logger.info(
        "run_rewrite_batch: finished profiles=%d attempted=%d ok=%d failed=%d",
        len(profiles),
        clusters_attempted,
        clusters_succeeded,
        clusters_failed,
    )
    return RewriteReport(
        profiles_processed=len(profiles),
        clusters_attempted=clusters_attempted,
        clusters_succeeded=clusters_succeeded,
        clusters_failed=clusters_failed,
    )


def run_rewrite_for_user(
    user_id: int, config: dict[str, Any] | None = None
) -> RewriteReport:
    """Process clusters needing rewrite for a single user's profile. Used after setup/settings save."""
    logger.info("run_rewrite_for_user: starting user_id=%d", user_id)
    cfg = config or load_config()
    profile = db_users.get_profile(user_id)
    if not profile:
        return RewriteReport(
            profiles_processed=0,
            clusters_attempted=0,
            clusters_succeeded=0,
            clusters_failed=0,
        )

    processing = cfg.get("processing", {})
    window_hours = processing.get("cluster_window_hours", 24)
    since = datetime.now(UTC) - timedelta(hours=window_hours)
    schedule_cfg = cfg.get("schedule", {})
    batch_size = schedule_cfg.get("rewrite_batch_size", 10)
    parallel_workers = schedule_cfg.get("rewrite_parallel_workers", 2)

    profile_hash = profile_service.compute_profile_hash(profile)
    clusters = db_clusters.get_clusters_needing_rewrite(
        profile_hash=profile_hash,
        since=since,
        limit=batch_size,
    )
    work: list[tuple[str, list[dict[str, Any]]]] = []
    for row in clusters:
        cluster_id = row["cluster_id"]
        articles = db_clusters.get_articles_in_cluster(cluster_id)
        if articles:
            work.append((cluster_id, articles))

    clusters_attempted = 0
    clusters_succeeded = 0
    clusters_failed = 0

    if not work:
        logger.info("run_rewrite_for_user: no work for user_id=%d", user_id)
        return RewriteReport(
            profiles_processed=1,
            clusters_attempted=0,
            clusters_succeeded=0,
            clusters_failed=0,
        )

    logger.info("run_rewrite_for_user: work=%d clusters, loading provider", len(work))
    provider = get_provider(cfg)
    logger.info("run_rewrite_for_user: provider ready")

    if parallel_workers > 1:
        with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
            futures = {
                executor.submit(
                    _rewrite_one,
                    cluster_id,
                    articles,
                    profile,
                    cfg,
                    provider,
                ): cluster_id
                for cluster_id, articles in work
            }
            for future in as_completed(futures):
                clusters_attempted += 1
                if future.result():
                    clusters_succeeded += 1
                else:
                    clusters_failed += 1
    else:
        for cluster_id, articles in work:
            clusters_attempted += 1
            if rewrite_cluster(
                cluster_id=cluster_id,
                articles=articles,
                profile=profile,
                config=cfg,
                provider=provider,
            ):
                clusters_succeeded += 1
            else:
                clusters_failed += 1

    logger.info(
        "run_rewrite_for_user: finished user_id=%d attempted=%d ok=%d failed=%d",
        user_id,
        clusters_attempted,
        clusters_succeeded,
        clusters_failed,
    )
    return RewriteReport(
        profiles_processed=1,
        clusters_attempted=clusters_attempted,
        clusters_succeeded=clusters_succeeded,
        clusters_failed=clusters_failed,
    )
