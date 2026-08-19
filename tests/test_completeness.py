from datetime import date

import pandas as pd

from enex_dam.completeness import find_incomplete_days


def test_find_incomplete_days_flags_missing_and_short_days():
    rows = []
    for hour in range(24):
        rows.append({"date": date(2025, 1, 1), "hour": hour, "mcp": 1.0})
    for hour in range(10):  # incomplete day
        rows.append({"date": date(2025, 1, 2), "hour": hour, "mcp": 1.0})
    # 2025-01-03 fully missing

    df = pd.DataFrame(rows)

    incomplete = find_incomplete_days(df, start=date(2025, 1, 1), end=date(2025, 1, 3))

    days = {entry.day: entry for entry in incomplete}
    assert date(2025, 1, 1) not in days
    assert days[date(2025, 1, 2)].found == 10
    assert days[date(2025, 1, 3)].found == 0


def test_find_incomplete_days_respects_known_exceptions():
    rows = [{"date": date(2025, 3, 30), "hour": h, "mcp": 1.0} for h in range(23)]
    df = pd.DataFrame(rows)

    incomplete = find_incomplete_days(df, start=date(2025, 3, 30), end=date(2025, 3, 30))

    assert incomplete == []
