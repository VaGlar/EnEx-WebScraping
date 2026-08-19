import pandas as pd
import pytest

from enex_dam.config import AVAILABILITY_FACTOR, PLANT_CAPACITY_MW, PLANT_EFFICIENCY
from enex_dam.economics import MissingMonthlyPrices, compute_monthly_profit


def test_compute_monthly_profit_matches_formula():
    mcp_df = pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-01"],
            "hour": [0, 1],
            "mcp": [100.0, 120.0],
        }
    )
    monthly_prices = pd.DataFrame(
        {"month": ["2026-01"], "ta": [10.0], "eta": [5.0], "ttf": [30.0]}
    )

    result = compute_monthly_profit(mcp_df, monthly_prices)

    assert list(result["month"]) == ["2026-01"]
    assert result["hours"].iloc[0] == 2

    expected_margin_0 = 100.0 + 10.0 - 5.0 - 30.0 / PLANT_EFFICIENCY
    expected_margin_1 = 120.0 + 10.0 - 5.0 - 30.0 / PLANT_EFFICIENCY
    expected_avg = (expected_margin_0 + expected_margin_1) / 2
    expected_profit = expected_avg * 2 * PLANT_CAPACITY_MW * AVAILABILITY_FACTOR

    assert result["avg_margin_eur_per_mwh"].iloc[0] == pytest.approx(expected_avg)
    assert result["profit_eur"].iloc[0] == pytest.approx(expected_profit)


def test_compute_monthly_profit_raises_on_missing_month():
    mcp_df = pd.DataFrame({"date": ["2026-02-01"], "hour": [0], "mcp": [100.0]})
    monthly_prices = pd.DataFrame(
        {"month": ["2026-01"], "ta": [10.0], "eta": [5.0], "ttf": [30.0]}
    )

    with pytest.raises(MissingMonthlyPrices):
        compute_monthly_profit(mcp_df, monthly_prices)


def test_compute_monthly_profit_empty_input():
    mcp_df = pd.DataFrame(columns=["date", "hour", "mcp"])
    monthly_prices = pd.DataFrame(columns=["month", "ta", "eta", "ttf"])

    result = compute_monthly_profit(mcp_df, monthly_prices)

    assert result.empty
