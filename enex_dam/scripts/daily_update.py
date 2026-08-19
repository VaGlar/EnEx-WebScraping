"""Fetch a single delivery day's DAM prices and append them to the dataset.

Usage:
    python -m enex_dam.scripts.daily_update [--date YYYY-MM-DD]

Defaults to today's date. Intended to run once a day (see the
`.github/workflows/daily_update.yml` scheduled workflow).
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime

from .. import storage
from ..dam import DamFileMalformed, DamFileNotAvailable, fetch_dam_hourly
from ..logging_config import configure_logging

logger = logging.getLogger(__name__)


def run(target_date: date) -> bool:
    """Fetch and store one day. Returns True if new data was written."""
    df = storage.load_data()

    if storage.has_date(df, target_date):
        logger.info("MCP values for %s already exist. Skipping.", target_date)
        return False

    try:
        hourly = fetch_dam_hourly(target_date)
    except DamFileNotAvailable as exc:
        logger.warning("DAM file not available for %s: %s", target_date, exc)
        return False
    except DamFileMalformed as exc:
        logger.error("DAM file for %s could not be parsed: %s", target_date, exc)
        return False

    merged = storage.merge_new_data(df, hourly)
    storage.save_data(merged)
    logger.info("Added %d hourly MCP records for %s.", len(hourly), target_date)
    return True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=date.today(),
        help="Delivery day to fetch (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose)
    logger.info("Starting daily update for %s", args.date)
    updated = run(args.date)
    logger.info("Daily update finished (data changed: %s).", updated)
    return 0


if __name__ == "__main__":
    sys.exit(main())
