"""Backfill the dataset over a date range by downloading each day's DAM file.

Usage:
    python -m enex_dam.scripts.bulk_download --start 2025-01-01 --end 2025-10-20
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime, timedelta

import requests

from .. import storage
from ..config import BULK_REQUEST_DELAY_SECONDS, DATA_START_DATE
from ..dam import DamFileMalformed, DamFileNotAvailable, fetch_dam_hourly
from ..logging_config import configure_logging

logger = logging.getLogger(__name__)


def run(start: date, end: date, skip_existing: bool = True) -> int:
    df = storage.load_data()
    session = requests.Session()
    fetched = 0
    try:
        day = start
        while day <= end:
            if skip_existing and storage.has_date(df, day):
                logger.debug("Skipping %s, already present.", day)
                day += timedelta(days=1)
                continue

            try:
                hourly = fetch_dam_hourly(day, session=session)
                df = storage.merge_new_data(df, hourly)
                fetched += 1
                logger.info("Fetched %s (%d hours).", day, len(hourly))
            except DamFileNotAvailable as exc:
                logger.warning("Skipping %s: %s", day, exc)
            except DamFileMalformed as exc:
                logger.error("Skipping %s: %s", day, exc)

            time.sleep(BULK_REQUEST_DELAY_SECONDS)
            day += timedelta(days=1)
    finally:
        session.close()

    storage.save_data(df)
    logger.info("Bulk download complete. %d new day(s) fetched.", fetched)
    return fetched


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    date_type = lambda s: datetime.strptime(s, "%Y-%m-%d").date()
    parser.add_argument("--start", type=date_type, default=date.fromisoformat(DATA_START_DATE))
    parser.add_argument("--end", type=date_type, default=date.today())
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(verbose=args.verbose)
    run(args.start, args.end)
    return 0


if __name__ == "__main__":
    sys.exit(main())
