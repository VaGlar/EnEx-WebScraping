from datetime import date

import pandas as pd

from enex_dam import storage


def test_load_data_missing_file_returns_empty_frame(tmp_path):
    df = storage.load_data(tmp_path / "nope.csv")
    assert list(df.columns) == storage.COLUMNS
    assert len(df) == 0


def test_merge_new_data_dedupes_and_keeps_latest(tmp_path):
    existing = pd.DataFrame(
        {"date": [date(2025, 1, 1)], "hour": [0], "mcp": [10.0]}
    )
    new_rows = pd.DataFrame(
        {"date": [date(2025, 1, 1), date(2025, 1, 2)], "hour": [0, 0], "mcp": [99.0, 5.0]}
    )

    merged = storage.merge_new_data(existing, new_rows)

    assert len(merged) == 2
    row = merged[(merged["date"] == date(2025, 1, 1)) & (merged["hour"] == 0)]
    assert row["mcp"].iloc[0] == 99.0


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "mcp.csv"
    df = pd.DataFrame(
        {"date": [date(2025, 1, 1), date(2025, 1, 1)], "hour": [1, 0], "mcp": [11.0, 10.0]}
    )
    storage.save_data(df, path)

    loaded = storage.load_data(path)
    assert list(loaded["hour"]) == [0, 1]
    assert loaded["date"].iloc[0] == date(2025, 1, 1)


def test_has_date(tmp_path):
    df = pd.DataFrame({"date": [date(2025, 1, 1)], "hour": [0], "mcp": [10.0]})
    assert storage.has_date(df, date(2025, 1, 1))
    assert not storage.has_date(df, date(2025, 1, 2))
