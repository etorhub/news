"""APScheduler entry point. Runs in the scheduler container only."""

import contextlib
import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import load_config
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


def _run_rewrite_job() -> None:
    """Scheduled job: rewrite today's articles for all profile hashes."""
    try:
        config = load_config()
        report = run_rewrite_batch(config)
        logger.info(
            "Rewrite run: profiles=%d attempted=%d ok=%d failed=%d",
            report.profiles_processed,
            report.articles_attempted,
            report.articles_succeeded,
            report.articles_failed,
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
