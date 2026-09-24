"""Cross-metric analysis helpers: monthly summary table, averages, correlations."""

from __future__ import annotations

import pandas as pd

from .config import PLANT_EFFICIENCY
from .economics import compute_monthly_profit

CORRELATION_PAIRS = [
    ("ttf", "profit_eur", "TTF ↔ Κέρδος"),
    ("ttf", "avg_mcp", "TTF ↔ MCP"),
    ("ttf", "mtfa", "TTF ↔ ΜΤΦΑ"),
    ("ttf", "revenue_side", "TTF ↔ (MCP+ΤΑ-ΕΤΑ)"),
    ("avg_mcp", "profit_eur", "MCP ↔ Κέρδος"),
]


def monthly_summary(mcp_df: pd.DataFrame, monthly_prices: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """One row per complete month: avg MCP, TA, ETA, TTF, MTFA, avg margin, profit,
    plus two breakeven-analysis columns:

    - ``revenue_side`` = avg_mcp + ta - eta (everything in the margin formula
      except the fuel cost term - the €/MWh the plant earns before TTF).
    - ``breakeven_ttf`` = revenue_side * PLANT_EFFICIENCY - the gas price at
      which margin hits exactly zero (solve margin=0 for TTF). Directly
      comparable to the actual ``ttf`` column since both are €/MWh gas.

    Reuses :func:`compute_monthly_profit` for which months qualify as
    "complete" (skips the same incomplete months, for the same reason).
    """
    profit_df, skipped = compute_monthly_profit(mcp_df, monthly_prices)
    if profit_df.empty:
        return pd.DataFrame(), skipped

    df = mcp_df.copy()
    df["month"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
    monthly_mcp = df.groupby("month", as_index=False)["mcp"].mean().rename(columns={"mcp": "avg_mcp"})

    summary = profit_df.merge(monthly_mcp, on="month").merge(monthly_prices, on="month")
    summary["revenue_side"] = summary["avg_mcp"] + summary["ta"] - summary["eta"]
    summary["breakeven_ttf"] = summary["revenue_side"] * PLANT_EFFICIENCY
    return summary.sort_values("month").reset_index(drop=True), skipped


def compute_correlations(summary: pd.DataFrame) -> list[dict]:
    """Pearson r for each pair in CORRELATION_PAIRS, skipping pairs with <3 points or all-NaN."""
    results = []
    for col_a, col_b, label in CORRELATION_PAIRS:
        if col_a not in summary.columns or col_b not in summary.columns:
            continue
        pair = summary[[col_a, col_b]].dropna()
        if len(pair) < 3:
            continue
        r = pair[col_a].corr(pair[col_b])
        results.append({"label": label, "r": r, "n": len(pair)})
    return results


def column_averages(summary: pd.DataFrame) -> dict:
    cols = [
        "avg_mcp", "ta", "eta", "ttf", "mtfa",
        "breakeven_ttf", "avg_margin_eur_per_mwh", "profit_eur",
    ]
    return {c: summary[c].mean() for c in cols if c in summary.columns}
