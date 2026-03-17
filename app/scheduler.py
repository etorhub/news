"""APScheduler entry point. Runs in the scheduler container only."""

import contextlib
import logging
from dataclasses import asdict
from typing import Any, Callable

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.clustering.service import run_cluster_and_embed
from app.clustering.service import StoryReport
from app.config import load_config
from app.db import admin as admin_db
from app.db import articles as articles_db
from app.extraction.extractor import enrich_all_articles
from app.feed.orchestrator import fetch_all_due_feeds
from app.services.rewrite_service import run_rewrite_batch

logger = logging.getLogger(__name__)


def _cluster_articles_guarded(config: dict[str, Any]) -> StoryReport:
    """Run clustering only when no articles are pending extraction."""
    pending = articles_db.get_pending_extraction_count()
    if pending > 0:
        logger.warning(
            "Skipping cluster job: %d articles still pending extraction",
            pending,
        )
        return StoryReport(
            articles_embedded=0,
            articles_clustered=0,
            stories_created=0,
        )
    return run_cluster_and_embed(config)


def _run_tracked_job(
    job_name: str, job_fn: Callable[[dict[str, Any]], Any]
) -> None:
    """Run a pipeline job with admin tracking. Wraps config load, execution, and result logging."""
    logger.info("Starting %s job", job_name)
    job_id = admin_db.insert_job_run(job_name)
    try:
        config = load_config()
        report = job_fn(config)
        admin_db.update_job_run(job_id, status="success", result=asdict(report))
        logger.info("%s job completed: %s", job_name, report)
    except Exception as e:
        admin_db.update_job_run(job_id, status="error", error_message=str(e))
        logger.exception("%s job failed", job_name)


def main() -> None:
    """Start the scheduler with fetch job."""
    import os

    if os.path.exists(".env"):
        from dotenv import load_dotenv

        load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    config = load_config()
    interval_min = config.get("schedule", {}).get("fetch_interval_minutes", 60)

    scheduler = BlockingScheduler()
    scheduler.add_job(
        lambda: _run_tracked_job("fetch_feeds", fetch_all_due_feeds),
        trigger=IntervalTrigger(minutes=interval_min),
        id="fetch_feeds",
    )

    enrichment_cron = config.get("schedule", {}).get("enrichment_cron", "10 * * * *")
    scheduler.add_job(
        lambda: _run_tracked_job("enrich_articles", enrich_all_articles),
        trigger=CronTrigger.from_crontab(enrichment_cron),
        id="enrich_articles",
    )

    cluster_cron = config.get("schedule", {}).get("cluster_cron", "5 * * * *")
    scheduler.add_job(
        lambda: _run_tracked_job("cluster_articles", _cluster_articles_guarded),
        trigger=CronTrigger.from_crontab(cluster_cron),
        id="cluster_articles",
    )

    rewrite_cron = config.get("schedule", {}).get("rewrite_cron", "0 6 * * *")
    scheduler.add_job(
        lambda: _run_tracked_job("rewrite_articles", run_rewrite_batch),
        trigger=CronTrigger.from_crontab(rewrite_cron),
        id="rewrite_articles",
    )

    logger.info(
        "Scheduler started: fetch every %d min, enrichment=%s, cluster=%s, rewrite=%s",
        interval_min,
        enrichment_cron,
        cluster_cron,
        rewrite_cron,
    )
    with contextlib.suppress(KeyboardInterrupt, SystemExit):
        scheduler.start()


if __name__ == "__main__":
    main()
