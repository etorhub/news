"""LLM rewrite orchestration. Runs on schedule or via manual trigger after settings save."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import load_config
from app.db import clusters as db_clusters
from app.db import users as db_users
from app.llm.prompts import load_prompt
from app.llm.provider import get_provider
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
    title_marker = "TITLE:"
    summary_marker = "SUMMARY:"
    full_marker = "FULL:"
    if (
        title_marker not in text
        or summary_marker not in text
        or full_marker not in text
    ):
        raise ValueError("Response missing TITLE:, SUMMARY:, or FULL: sections")

    parts = text.split(full_marker, 1)
    if len(parts) != 2:
        raise ValueError("Response missing FULL: section")
    header_part = parts[0]
    full_text = parts[1].strip()

    title = ""
    if title_marker in header_part:
        title_section = header_part.split(title_marker, 1)[1]
        if summary_marker in title_section:
            title_section = title_section.split(summary_marker, 1)[0]
        title = title_section.strip()

    summary = ""
    if summary_marker in header_part:
        summary_section = header_part.split(summary_marker, 1)[1]
        if full_marker in summary_section:
            summary_section = summary_section.split(full_marker, 1)[0]
        summary = summary_section.strip()

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
) -> bool:
    """Rewrite a cluster (merge + adapt all articles) and store. Returns True on success."""
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

    try:
        provider = get_provider(config)
        response = provider.complete(prompt, max_tokens=3000)
        title, summary, full_text = _parse_cluster_llm_response(response)
        db_clusters.insert_cluster_rewrite(
            cluster_id=cluster_id,
            profile_hash=profile_hash,
            title=title,
            summary=summary,
            full_text=full_text,
            rewrite_failed=False,
        )
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
        return False


def run_rewrite_batch(config: dict[str, Any]) -> RewriteReport:
    """Process today's clusters for all distinct rewrite profiles."""
    processing = config.get("processing", {})
    window_hours = processing.get("cluster_window_hours", 24)
    since = datetime.now(UTC) - timedelta(hours=window_hours)
    batch_size = config.get("schedule", {}).get("rewrite_batch_size", 10)

    profiles = db_users.get_distinct_rewrite_profiles()
    clusters_attempted = 0
    clusters_succeeded = 0
    clusters_failed = 0

    for profile in profiles:
        profile_hash = profile_service.compute_profile_hash(profile)
        clusters = db_clusters.get_clusters_needing_rewrite(
            profile_hash=profile_hash,
            since=since,
            limit=batch_size,
        )
        for row in clusters:
            cluster_id = row["cluster_id"]
            articles = db_clusters.get_articles_in_cluster(cluster_id)
            if not articles:
                continue
            clusters_attempted += 1
            if rewrite_cluster(
                cluster_id=cluster_id,
                articles=articles,
                profile=profile,
                config=config,
            ):
                clusters_succeeded += 1
            else:
                clusters_failed += 1

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
    batch_size = cfg.get("schedule", {}).get("rewrite_batch_size", 10)

    profile_hash = profile_service.compute_profile_hash(profile)
    clusters = db_clusters.get_clusters_needing_rewrite(
        profile_hash=profile_hash,
        since=since,
        limit=batch_size,
    )
    clusters_attempted = 0
    clusters_succeeded = 0
    clusters_failed = 0

    for row in clusters:
        cluster_id = row["cluster_id"]
        articles = db_clusters.get_articles_in_cluster(cluster_id)
        if not articles:
            continue
        clusters_attempted += 1
        if rewrite_cluster(
            cluster_id=cluster_id,
            articles=articles,
            profile=profile,
            config=cfg,
        ):
            clusters_succeeded += 1
        else:
            clusters_failed += 1

    return RewriteReport(
        profiles_processed=1,
        clusters_attempted=clusters_attempted,
        clusters_succeeded=clusters_succeeded,
        clusters_failed=clusters_failed,
    )
