"""APScheduler entry point. Runs in the scheduler container only."""

import contextlib
import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import load_config
from app.feed.orchestrator import fetch_all_due_feeds

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

    with contextlib.suppress(KeyboardInterrupt, SystemExit):
        scheduler.start()


if __name__ == "__main__":
    main()
