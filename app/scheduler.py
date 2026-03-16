"""APScheduler entry point. Runs in the scheduler container only."""

import contextlib

from apscheduler.schedulers.blocking import BlockingScheduler


def main() -> None:
    """Start the scheduler and block. No jobs registered yet."""
    scheduler = BlockingScheduler()
    with contextlib.suppress(KeyboardInterrupt, SystemExit):
        scheduler.start()


if __name__ == "__main__":
    main()
