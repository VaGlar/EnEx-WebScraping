"""Generate the static HTML dashboard at docs/index.html.

Usage:
    python -m enex_dam.scripts.build_dashboard [--out docs/index.html]

Reads data/mcp_full.csv and data/monthly_prices.csv and writes a single
self-contained HTML file with no external assets, suitable for GitHub Pages.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .. import storage
from ..config import REPO_ROOT
from ..dashboard import build_dashboard_html
from ..economics import load_monthly_prices
from ..logging_config import configure_logging

logger = logging.getLogger(__name__)

DEFAULT_OUT = REPO_ROOT / "docs" / "index.html"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output HTML path.")
    args = parser.parse_args(argv)

    configure_logging()
    mcp_df = storage.load_data()
    monthly_prices = load_monthly_prices()

    html_doc = build_dashboard_html(mcp_df, monthly_prices)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html_doc, encoding="utf-8")
    logger.info("Wrote dashboard to %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
