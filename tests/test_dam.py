from datetime import date
from io import BytesIO

import pandas as pd
import pytest
import responses

from enex_dam.dam import DamFileMalformed, DamFileNotAvailable, fetch_dam_hourly, _dam_url


def _make_workbook(rows):
    df = pd.DataFrame(rows, columns=["DELIVERY_MTU", "MCP", "DDAY"])
    buf = BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


@responses.activate
def test_fetch_dam_hourly_averages_quarter_hours():
    day = date(2025, 1, 2)
    rows = [
        ("2025-01-02 00:00", 10.0, 20250102),
        ("2025-01-02 00:15", 20.0, 20250102),
        ("2025-01-02 00:30", 30.0, 20250102),
        ("2025-01-02 00:45", 40.0, 20250102),
        ("2025-01-02 01:00", 5.0, 20250102),
    ]
    responses.add(responses.GET, _dam_url(day), body=_make_workbook(rows), status=200)

    result = fetch_dam_hourly(day)

    assert list(result["hour"]) == [0, 1]
    assert result.loc[result["hour"] == 0, "mcp"].iloc[0] == pytest.approx(25.0)
    assert result.loc[result["hour"] == 1, "mcp"].iloc[0] == pytest.approx(5.0)
    assert all(result["date"] == day)


@responses.activate
def test_fetch_dam_hourly_missing_file_raises():
    day = date(2025, 1, 3)
    responses.add(responses.GET, _dam_url(day), status=404)

    with pytest.raises(DamFileNotAvailable):
        fetch_dam_hourly(day)


@responses.activate
def test_fetch_dam_hourly_malformed_columns_raises():
    day = date(2025, 1, 4)
    df = pd.DataFrame({"UNEXPECTED": [1, 2, 3]})
    buf = BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    responses.add(responses.GET, _dam_url(day), body=buf.getvalue(), status=200)

    with pytest.raises(DamFileMalformed):
        fetch_dam_hourly(day)
