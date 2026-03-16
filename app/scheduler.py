"""APScheduler entry point. Runs in the scheduler container only."""

import contextlib
import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.clustering.service import run_cluster_and_embed
from app.config import load_config
from app.extraction.extractor import enrich_articles
from app.feed.orchestrator import fetch_all_due_feeds
from app.services.rewrite_service import run_rewrite_batch

logger = logging.getLogger(__name__)


def _run_fetch_job() -> None:
    """Scheduled job: fetch all due feeds."""
    try:
        config = load_config()
        report = fetch_all_due_feeds(config)
        logger.info(
            "Fetch run: checked=%d fetched=%d inserted=%d deactivated=%d",
            report.feeds_checked,
            report.feeds_fetched,
            report.articles_inserted,
            report.feeds_deactivated,
        )
    except Exception:
        logger.exception("Fetch job failed")


def _run_enrichment_job() -> None:
    """Scheduled job: extract full article content for pending articles."""
    try:
        config = load_config()
        report = enrich_articles(config)
        logger.info(
            "Enrichment run: checked=%d extracted=%d failed=%d skipped=%d",
            report.articles_checked,
            report.articles_extracted,
            report.articles_failed,
            report.articles_skipped,
        )
    except Exception:
        logger.exception("Enrichment job failed")


def _run_cluster_job() -> None:
    """Scheduled job: embed and cluster today's articles."""
    try:
        config = load_config()
        report = run_cluster_and_embed(config)
        logger.info(
            "Cluster run: embedded=%d clustered=%d clusters_created=%d",
            report.articles_embedded,
            report.articles_clustered,
            report.clusters_created,
        )
    except Exception:
        logger.exception("Cluster job failed")


def _run_rewrite_job() -> None:
    """Scheduled job: rewrite today's articles for all profile hashes."""
    try:
        config = load_config()
        report = run_rewrite_batch(config)
        logger.info(
            "Rewrite run: profiles=%d clusters_attempted=%d ok=%d failed=%d",
            report.profiles_processed,
            report.clusters_attempted,
            report.clusters_succeeded,
            report.clusters_failed,
        )
    except Exception:
        logger.exception("Rewrite job failed")


def main() -> None:
    """Start the scheduler with fetch job."""
    import os

    if os.path.exists(".env"):
        from dotenv import load_dotenv

        load_dotenv()

    config = load_config()
    interval_min = config.get("schedule", {}).get("fetch_interval_minutes", 60)

    scheduler = BlockingScheduler()
    scheduler.add_job(
        _run_fetch_job,
        trigger=IntervalTrigger(minutes=interval_min),
        id="fetch_feeds",
    )

    enrichment_cron = config.get("schedule", {}).get("enrichment_cron", "10 * * * *")
    scheduler.add_job(
        _run_enrichment_job,
        trigger=CronTrigger.from_crontab(enrichment_cron),
        id="enrich_articles",
    )

    cluster_cron = config.get("schedule", {}).get("cluster_cron", "5 * * * *")
    scheduler.add_job(
        _run_cluster_job,
        trigger=CronTrigger.from_crontab(cluster_cron),
        id="cluster_articles",
    )

    rewrite_cron = config.get("schedule", {}).get("rewrite_cron", "0 6 * * *")
    scheduler.add_job(
        _run_rewrite_job,
        trigger=CronTrigger.from_crontab(rewrite_cron),
        id="rewrite_articles",
    )

    with contextlib.suppress(KeyboardInterrupt, SystemExit):
        scheduler.start()


if __name__ == "__main__":
    main()
