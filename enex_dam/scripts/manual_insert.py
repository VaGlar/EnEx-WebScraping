"""Interactively fetch and insert MCP values for one or more specific dates.

Usage:
    python -m enex_dam.scripts.manual_insert
    (enter dates as YYYY-MM-DD, empty line to quit)
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime

from .. import storage
from ..completeness import find_incomplete_days
from ..dam import DamFileMalformed, DamFileNotAvailable, fetch_dam_hourly
from ..logging_config import configure_logging

logger = logging.getLogger(__name__)


def report_missing(df) -> None:
    incomplete = find_incomplete_days(df)
    if incomplete:
        logger.info("Missing or incomplete days remaining: %d", len(incomplete))
        for entry in incomplete:
            logger.info("  %s - expected %d, found %d", entry.day, entry.expected, entry.found)
    else:
        logger.info("All dates have the expected number of hourly records.")


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    df = storage.load_data()
    report_missing(df)

    while True:
        raw = input("Add date (YYYY-MM-DD), or press Enter to quit: ").strip()
        if not raw:
            logger.info("Exiting.")
            break

        try:
            target_date = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            logger.error("Invalid date format: %s", raw)
            continue

        if storage.has_date(df, target_date):
            logger.info("%s already present, skipping.", target_date)
            continue

        try:
            hourly = fetch_dam_hourly(target_date)
        except DamFileNotAvailable as exc:
            logger.warning("%s", exc)
            continue
        except DamFileMalformed as exc:
            logger.error("%s", exc)
            continue

        df = storage.merge_new_data(df, hourly)
        storage.save_data(df)
        logger.info("Inserted %d records for %s.", len(hourly), target_date)
        report_missing(df)

    return 0


if __name__ == "__main__":
    sys.exit(main())
