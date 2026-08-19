"""Detect missing or incomplete delivery days in the stored dataset."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from .config import DATA_START_DATE, EXPECTED_HOURLY_RECORD_EXCEPTIONS


@dataclass
class MissingDay:
    day: date
    expected: int
    found: int


def expected_record_count(day: date) -> int:
    return EXPECTED_HOURLY_RECORD_EXCEPTIONS.get(day.isoformat(), 24)


def find_incomplete_days(
    df: pd.DataFrame,
    start: date | None = None,
    end: date | None = None,
) -> list[MissingDay]:
    """Return every day in [start, end] whose record count doesn't match expectations."""
    start = start or date.fromisoformat(DATA_START_DATE)
    end = end or date.today()

    counts = df.groupby("date").size().to_dict()

    incomplete = []
    day = start
    while day <= end:
        expected = expected_record_count(day)
        found = counts.get(day, 0)
        if found != expected:
            incomplete.append(MissingDay(day=day, expected=expected, found=found))
        day += timedelta(days=1)
    return incomplete
