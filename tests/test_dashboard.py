import pandas as pd

from enex_dam.dashboard import build_dashboard_html


def test_build_dashboard_html_with_data():
    mcp_df = pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-01", "2026-01-02", "2026-01-02"],
            "hour": [0, 1, 0, 1],
            "mcp": [100.0, 120.0, 90.0, 110.0],
        }
    )
    monthly_prices = pd.DataFrame(
        {"month": ["2026-01"], "ta": [10.0], "eta": [5.0], "ttf": [30.0]}
    )

    result = build_dashboard_html(mcp_df, monthly_prices)

    assert "<!doctype html>" in result
    assert "2026-01-01" in result
    assert "viz-line" in result
    assert "viz-bar" in result


def test_build_dashboard_html_empty_data():
    mcp_df = pd.DataFrame(columns=["date", "hour", "mcp"])
    monthly_prices = pd.DataFrame(columns=["month", "ta", "eta", "ttf"])

    result = build_dashboard_html(mcp_df, monthly_prices)

    assert "<!doctype html>" in result
    assert "Δεν υπάρχουν ακόμα δεδομένα" in result


def test_build_dashboard_html_reports_skipped_months():
    mcp_df = pd.DataFrame({"date": ["2026-02-01"], "hour": [0], "mcp": [100.0]})
    monthly_prices = pd.DataFrame(
        {"month": ["2026-02"], "ta": [10.0], "eta": [None], "ttf": [30.0]}
    )

    result = build_dashboard_html(mcp_df, monthly_prices)

    assert "2026-02" in result
    assert "eta" in result
