"""Load, merge and persist the hourly MCP dataset as a CSV file."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import DATA_FILE

COLUMNS = ["date", "hour", "mcp"]


def load_data(path: Path = DATA_FILE) -> pd.DataFrame:
    """Load the stored dataset, or an empty (correctly-typed) frame if none exists."""
    if not path.exists():
        return pd.DataFrame({"date": pd.Series(dtype="object"),
                              "hour": pd.Series(dtype="int64"),
                              "mcp": pd.Series(dtype="float64")})

    df = pd.read_csv(path, parse_dates=["date"])
    df["date"] = df["date"].dt.date
    return df[COLUMNS]


def save_data(df: pd.DataFrame, path: Path = DATA_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = df[COLUMNS].sort_values(["date", "hour"]).reset_index(drop=True)
    ordered.to_csv(path, index=False)


def merge_new_data(existing: pd.DataFrame, new_rows: pd.DataFrame) -> pd.DataFrame:
    """Combine existing and freshly-fetched rows, keeping the newest value per (date, hour)."""
    new_rows = new_rows.rename(columns={"mcp": "mcp"})[COLUMNS]
    combined = pd.concat([existing, new_rows], ignore_index=True)
    combined = combined.drop_duplicates(subset=["date", "hour"], keep="last")
    return combined.sort_values(["date", "hour"]).reset_index(drop=True)


def has_date(df: pd.DataFrame, day) -> bool:
    return bool((df["date"] == day).any())
