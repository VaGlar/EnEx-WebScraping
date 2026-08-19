"""Monthly profit calculation for the 1 MW gas-fired generation unit.

Per-hour margin (EUR/MWh electricity):

    margin = MCP + TA - ETA - (TTF / PLANT_EFFICIENCY)

TA (Τιμή Αναφοράς), ETA (Ειδικό Τέλος Ανανεώσιμων) and TTF (natural gas
reference price) are monthly constants supplied in ``data/monthly_prices.csv``.
TTF is a gas price (EUR/MWh gas), so it's divided by the plant's efficiency
to express it as a fuel cost per MWh of electricity produced.

Monthly profit sums that margin over every hour on record for the month,
scaled by the plant's capacity and its assumed availability factor (it
doesn't run every hour of every day - see config.AVAILABILITY_FACTOR).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import (
    AVAILABILITY_FACTOR,
    MONTHLY_PRICES_FILE,
    PLANT_CAPACITY_MW,
    PLANT_EFFICIENCY,
)

MONTHLY_PRICE_COLUMNS = ["month", "ta", "eta", "ttf"]


class MissingMonthlyPrices(Exception):
    """Raised when MCP data covers a month with no TA/ETA/TTF entry."""


def load_monthly_prices(path: Path = MONTHLY_PRICES_FILE) -> pd.DataFrame:
    """Load the monthly TA/ETA/TTF reference prices (EUR/MWh each)."""
    if not path.exists():
        return pd.DataFrame({col: pd.Series(dtype="object" if col == "month" else "float64")
                              for col in MONTHLY_PRICE_COLUMNS})

    df = pd.read_csv(path, dtype={"month": str})
    return df[MONTHLY_PRICE_COLUMNS]


def compute_monthly_profit(mcp_df: pd.DataFrame, monthly_prices: pd.DataFrame) -> pd.DataFrame:
    """Compute monthly profit (EUR) for the plant from hourly MCP data.

    ``mcp_df`` needs ``date``, ``hour``, ``mcp`` columns (as returned by
    :func:`enex_dam.storage.load_data`). Returns one row per month with the
    total profit and the average per-MWh margin.
    """
    if mcp_df.empty:
        return pd.DataFrame(columns=["month", "hours", "avg_margin_eur_per_mwh", "profit_eur"])

    df = mcp_df.copy()
    df["month"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")

    data_months = set(df["month"].unique())
    priced_months = set(monthly_prices["month"])
    missing = sorted(data_months - priced_months)
    if missing:
        raise MissingMonthlyPrices(
            f"No TA/ETA/TTF prices found for month(s): {missing}. "
            f"Add them to {MONTHLY_PRICES_FILE}."
        )

    merged = df.merge(monthly_prices, on="month", how="left")
    merged["margin"] = (
        merged["mcp"] + merged["ta"] - merged["eta"] - merged["ttf"] / PLANT_EFFICIENCY
    )

    grouped = merged.groupby("month", as_index=False).agg(
        hours=("margin", "size"),
        avg_margin_eur_per_mwh=("margin", "mean"),
    )
    grouped["profit_eur"] = (
        grouped["avg_margin_eur_per_mwh"]
        * grouped["hours"]
        * PLANT_CAPACITY_MW
        * AVAILABILITY_FACTOR
    )
    return grouped.sort_values("month").reset_index(drop=True)
