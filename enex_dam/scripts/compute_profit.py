"""Compute the plant's monthly profit from stored MCP data and TA/ETA/TTF prices.

Usage:
    python -m enex_dam.scripts.compute_profit [--out FILE.csv]

Reads data/mcp_full.csv and data/monthly_prices.csv, prints a per-month
table (hours, average margin EUR/MWh, profit EUR), and optionally writes it
to a CSV file.
"""

from __future__ import annotations

import argparse
import logging
import sys

from .. import storage
from ..economics import MissingMonthlyPrices, compute_monthly_profit, load_monthly_prices
from ..logging_config import configure_logging

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=str, default=None, help="Optional CSV path to write the result to.")
    args = parser.parse_args(argv)

    configure_logging()
    mcp_df = storage.load_data()
    monthly_prices = load_monthly_prices()

    try:
        result = compute_monthly_profit(mcp_df, monthly_prices)
    except MissingMonthlyPrices as exc:
        logger.error("%s", exc)
        return 1

    if result.empty:
        logger.info("No data available yet.")
        return 0

    print(result.to_string(index=False, formatters={
        "avg_margin_eur_per_mwh": "{:.2f}".format,
        "profit_eur": "{:.2f}".format,
    }))

    if args.out:
        result.to_csv(args.out, index=False)
        logger.info("Wrote monthly profit table to %s", args.out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
