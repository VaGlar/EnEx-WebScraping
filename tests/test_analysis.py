import pandas as pd
import pytest

from enex_dam.analysis import column_averages, compute_correlations, monthly_summary


def _sample_data():
    rows = []
    for month, mcp in [("2026-01", 100.0), ("2026-02", 110.0), ("2026-03", 90.0)]:
        rows.append({"date": f"{month}-01", "hour": 0, "mcp": mcp})
    mcp_df = pd.DataFrame(rows)
    monthly_prices = pd.DataFrame(
        {
            "month": ["2026-01", "2026-02", "2026-03"],
            "ta": [10.0, 10.0, 10.0],
            "eta": [5.0, 5.0, 5.0],
            "ttf": [20.0, 40.0, 30.0],
            "mtfa": [30.0, 60.0, 45.0],
        }
    )
    return mcp_df, monthly_prices


def test_monthly_summary_merges_all_columns():
    mcp_df, monthly_prices = _sample_data()

    summary, skipped = monthly_summary(mcp_df, monthly_prices)

    assert skipped == []
    assert list(summary["month"]) == ["2026-01", "2026-02", "2026-03"]
    assert "avg_mcp" in summary.columns
    assert "profit_eur" in summary.columns
    assert "mtfa" in summary.columns


def test_compute_correlations_perfect_linear_relationship():
    mcp_df, monthly_prices = _sample_data()
    summary, _ = monthly_summary(mcp_df, monthly_prices)

    correlations = compute_correlations(summary)
    by_label = {c["label"]: c for c in correlations}

    assert by_label["TTF ↔ ΜΤΦΑ"]["r"] == pytest.approx(1.0)
    assert by_label["TTF ↔ ΜΤΦΑ"]["n"] == 3


def test_compute_correlations_skips_short_series():
    mcp_df, monthly_prices = _sample_data()
    summary, _ = monthly_summary(mcp_df.iloc[:1], monthly_prices)

    correlations = compute_correlations(summary)

    assert correlations == []


def test_column_averages():
    mcp_df, monthly_prices = _sample_data()
    summary, _ = monthly_summary(mcp_df, monthly_prices)

    averages = column_averages(summary)

    assert averages["ttf"] == pytest.approx(30.0)
    assert averages["avg_mcp"] == pytest.approx(100.0)
