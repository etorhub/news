"""LLM rewrite orchestration. Runs on schedule, never during request handling."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.db import rewrites as db_rewrites
from app.db import users as db_users
from app.llm.prompts import load_prompt
from app.llm.provider import LLMProviderError, get_provider
from app.services import profile_service


@dataclass
class RewriteReport:
    """Summary of a rewrite batch run."""

    profiles_processed: int
    articles_attempted: int
    articles_succeeded: int
    articles_failed: int


def _parse_llm_response(text: str) -> tuple[str, str]:
    """Parse LLM output into (summary, full_text). Raises ValueError on bad format."""
    summary_marker = "SUMMARY:"
    full_marker = "FULL:"
    if summary_marker not in text or full_marker not in text:
        raise ValueError("Response missing SUMMARY: or FULL: sections")
    parts = text.split(full_marker, 1)
    if len(parts) != 2:
        raise ValueError("Response missing FULL: section")
    summary_part = parts[0]
    full_part = parts[1].strip()
    if summary_marker in summary_part:
        summary_part = summary_part.split(summary_marker, 1)[1]
    summary = summary_part.strip()
    if not summary or not full_part:
        raise ValueError("Empty SUMMARY or FULL section")
    return (summary, full_part)


def rewrite_one(
    article_id: str,
    article: dict[str, Any],
    profile: dict[str, Any],
    config: dict[str, Any],
) -> bool:
    """Rewrite one article and store. Returns True on success, False on failure."""
    article_text = (article.get("full_text") or "").strip() or (
        article.get("raw_text") or ""
    ).strip()
    if not article_text:
        db_rewrites.insert_rewrite(
            article_id=article_id,
            profile_hash=profile_service.compute_profile_hash(profile),
            summary=None,
            full_text=None,
            rewrite_failed=True,
        )
        return False

    profile_hash = profile_service.compute_profile_hash(profile)
    processing = config.get("processing", {})
    summary_sentences = processing.get("summary_sentences", 3)
    prompt_template = load_prompt("rewrite_article")
    prompt = prompt_template.format(
        article_text=article_text,
        language=profile.get("language", "ca"),
        rewrite_tone=profile.get(
            "rewrite_tone",
            "Short sentences. Simple vocabulary. No jargon.",
        ),
        filter_negative=str(profile.get("filter_negative", False)).lower(),
        summary_sentences=summary_sentences,
    )

    try:
        provider = get_provider(config)
        response = provider.complete(prompt, max_tokens=2000)
        summary, full_text = _parse_llm_response(response)
        db_rewrites.insert_rewrite(
            article_id=article_id,
            profile_hash=profile_hash,
            summary=summary,
            full_text=full_text,
            rewrite_failed=False,
        )
        return True
    except (LLMProviderError, ValueError):
        db_rewrites.insert_rewrite(
            article_id=article_id,
            profile_hash=profile_hash,
            summary=None,
            full_text=None,
            rewrite_failed=True,
        )
        return False


def run_rewrite_batch(config: dict[str, Any]) -> RewriteReport:
    """Process today's articles for all distinct rewrite profiles."""
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    batch_size = config.get("schedule", {}).get("rewrite_batch_size", 10)

    profiles = db_users.get_distinct_rewrite_profiles()
    articles_attempted = 0
    articles_succeeded = 0
    articles_failed = 0

    for profile in profiles:
        profile_hash = profile_service.compute_profile_hash(profile)
        articles = db_rewrites.get_articles_needing_rewrite(
            profile_hash=profile_hash,
            since=today_start,
            limit=batch_size,
        )
        for article in articles:
            articles_attempted += 1
            if rewrite_one(
                article_id=article["id"],
                article=article,
                profile=profile,
                config=config,
            ):
                articles_succeeded += 1
            else:
                articles_failed += 1

    return RewriteReport(
        profiles_processed=len(profiles),
        articles_attempted=articles_attempted,
        articles_succeeded=articles_succeeded,
        articles_failed=articles_failed,
    )
