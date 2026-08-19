"""Report delivery days with a missing or incomplete set of hourly MCP records.

Usage:
    python -m enex_dam.scripts.check_missing
"""

from __future__ import annotations

import logging
import sys

from .. import storage
from ..completeness import find_incomplete_days
from ..logging_config import configure_logging

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    df = storage.load_data()
    incomplete = find_incomplete_days(df)

    if not incomplete:
        logger.info("All dates have the expected number of hourly records.")
        return 0

    logger.warning("Found %d day(s) with missing or incomplete data:", len(incomplete))
    for entry in incomplete:
        logger.warning("  %s - expected %d, found %d", entry.day, entry.expected, entry.found)
    return 1


if __name__ == "__main__":
    sys.exit(main())
