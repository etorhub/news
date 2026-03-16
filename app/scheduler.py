"""APScheduler entry point. Runs in the scheduler container only."""

import contextlib
import logging
from dataclasses import asdict
from typing import Any, Callable

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.clustering.service import run_cluster_and_embed
from app.config import load_config
from app.db import admin as admin_db
from app.db import rewrite_requests as rewrite_requests_db
from app.extraction.extractor import enrich_articles
from app.feed.orchestrator import fetch_all_due_feeds
from app.services.rewrite_service import run_rewrite_batch, run_rewrite_for_user

logger = logging.getLogger(__name__)


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


def _poll_rewrite_requests() -> None:
    """Poll for on-demand rewrite requests (from setup/settings save)."""
    claimed = rewrite_requests_db.claim_pending_requests()
    if not claimed:
        return
    config = load_config()
    for row in claimed:
        request_id = row["id"]
        user_id = row["user_id"]
        try:
            run_rewrite_for_user(user_id, config)
            rewrite_requests_db.mark_done(request_id)
            logger.info("On-demand rewrite completed for user_id=%d", user_id)
        except Exception as e:
            rewrite_requests_db.mark_failed(request_id, str(e))
            logger.exception("On-demand rewrite failed for user_id=%d", user_id)


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
        lambda: _run_tracked_job("enrich_articles", enrich_articles),
        trigger=CronTrigger.from_crontab(enrichment_cron),
        id="enrich_articles",
    )

    cluster_cron = config.get("schedule", {}).get("cluster_cron", "5 * * * *")
    scheduler.add_job(
        lambda: _run_tracked_job("cluster_articles", run_cluster_and_embed),
        trigger=CronTrigger.from_crontab(cluster_cron),
        id="cluster_articles",
    )

    rewrite_cron = config.get("schedule", {}).get("rewrite_cron", "0 6 * * *")
    scheduler.add_job(
        lambda: _run_tracked_job("rewrite_articles", run_rewrite_batch),
        trigger=CronTrigger.from_crontab(rewrite_cron),
        id="rewrite_articles",
    )

    scheduler.add_job(
        _poll_rewrite_requests,
        trigger=IntervalTrigger(seconds=60),
        id="poll_rewrite_requests",
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
