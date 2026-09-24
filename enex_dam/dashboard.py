"""Build a static HTML dashboard (docs/index.html) from the collected MCP data.

No JS build step, no external assets: everything (data, styles, minimal
interaction script) is inlined into a single self-contained HTML file, so it
can be served as-is from GitHub Pages.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone

import pandas as pd

from .analysis import column_averages, compute_correlations, monthly_summary
from .completeness import find_incomplete_days
from .economics import compute_monthly_profit
from .config import PLANT_CAPACITY_MW, PLANT_EFFICIENCY

METRIC_LABELS = {
    "avg_mcp": "MCP", "ta": "ΤΑ", "eta": "ΕΤΑ", "ttf": "TTF",
    "mtfa": "ΜΤΦΑ", "avg_margin_eur_per_mwh": "Margin", "profit_eur": "Κέρδος",
    "revenue_side": "MCP+ΤΑ-ΕΤΑ", "breakeven_ttf": "Breakeven TTF",
}
METRIC_UNITS = {
    "avg_mcp": "€/MWh", "ta": "€/MWh", "eta": "€/MWh", "ttf": "€/MWh",
    "mtfa": "€/MWh", "avg_margin_eur_per_mwh": "€/MWh", "profit_eur": "€",
    "revenue_side": "€/MWh", "breakeven_ttf": "€/MWh",
}

MONTH_LABELS_EL = {
    "01": "Ιαν", "02": "Φεβ", "03": "Μαρ", "04": "Απρ", "05": "Μάι", "06": "Ιουν",
    "07": "Ιουλ", "08": "Αυγ", "09": "Σεπ", "10": "Οκτ", "11": "Νοε", "12": "Δεκ",
}


def _daily_avg_mcp(mcp_df: pd.DataFrame) -> pd.DataFrame:
    df = mcp_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    daily = df.groupby("date", as_index=False)["mcp"].mean().sort_values("date")
    daily["date_str"] = daily["date"].dt.strftime("%Y-%m-%d")
    return daily[["date_str", "mcp"]]


def _month_label(month: str) -> str:
    year, mm = month.split("-")
    return f"{MONTH_LABELS_EL.get(mm, mm)} {year[2:]}"


def _svg_line_chart(points: list[tuple[str, float]], width=1200, height=300) -> str:
    if not points:
        return '<p class="viz-empty">Δεν υπάρχουν ακόμα δεδομένα.</p>'

    pad_l, pad_r, pad_t, pad_b = 48, 16, 16, 28
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    values = [v for _, v in points]
    y_min, y_max = min(values), max(values)
    if y_min == y_max:
        y_min -= 1
        y_max += 1
    y_pad = (y_max - y_min) * 0.08
    y_min -= y_pad
    y_max += y_pad

    n = len(points)

    def x_of(i: int) -> float:
        return pad_l + (plot_w * i / (n - 1) if n > 1 else plot_w / 2)

    def y_of(v: float) -> float:
        return pad_t + plot_h - (v - y_min) / (y_max - y_min) * plot_h

    coords = [(x_of(i), y_of(v)) for i, (_, v) in enumerate(points)]
    path_d = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    area_d = path_d + f" L {coords[-1][0]:.1f},{pad_t + plot_h:.1f} L {coords[0][0]:.1f},{pad_t + plot_h:.1f} Z"

    grid_lines = []
    tick_count = 4
    for i in range(tick_count + 1):
        gy = pad_t + plot_h * i / tick_count
        val = y_max - (y_max - y_min) * i / tick_count
        grid_lines.append(
            f'<line class="viz-grid" x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" y2="{gy:.1f}" />'
            f'<text class="viz-axis-label" x="{pad_l - 8}" y="{gy + 4:.1f}" text-anchor="end">{val:,.0f}</text>'
        )

    x_labels = []
    label_idx = sorted(set([0, n // 4, n // 2, (3 * n) // 4, n - 1])) if n > 1 else [0]
    for i in label_idx:
        anchor = "start" if i == 0 else "end" if i == n - 1 else "middle"
        x_labels.append(
            f'<text class="viz-axis-label" x="{coords[i][0]:.1f}" y="{height - 6}" text-anchor="{anchor}">'
            f'{html.escape(points[i][0])}</text>'
        )

    end_x, end_y = coords[-1]
    data_json = json.dumps([{"x": x, "y": y, "date": d, "value": v} for (x, y), (d, v) in zip(coords, points)])

    return f"""
<div class="viz-chart-wrap" data-chart="line">
  <svg viewBox="0 0 {width} {height}" class="viz-svg" role="img"
       aria-label="Ημερήσια μέση τιμή MCP, {html.escape(points[0][0])} έως {html.escape(points[-1][0])}">
    {''.join(grid_lines)}
    <path class="viz-area" d="{area_d}" />
    <path class="viz-line" d="{path_d}" />
    <circle class="viz-end-dot" cx="{end_x:.1f}" cy="{end_y:.1f}" r="4.5" />
    {''.join(x_labels)}
    <rect class="viz-hit-rect" x="{pad_l}" y="{pad_t}" width="{plot_w}" height="{plot_h}"
          data-points='{data_json}' />
  </svg>
  <div class="viz-tooltip" hidden></div>
  <div class="viz-crosshair" hidden></div>
</div>
"""


def _svg_bar_chart(bars: list[tuple[str, float]], width=1200, height=300, unit="€") -> str:
    if not bars:
        return '<p class="viz-empty">Δεν υπάρχουν ακόμα πλήρεις μήνες.</p>'

    pad_l, pad_r, pad_t, pad_b = 64, 16, 16, 28
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    values = [v for _, v in bars]
    y_max = max(max(values), 0) * 1.15 or 1
    y_min = min(min(values), 0)

    n = len(bars)
    slot_w = plot_w / n
    bar_w = min(24, slot_w * 0.55)

    def y_of(v: float) -> float:
        return pad_t + plot_h - (v - y_min) / (y_max - y_min) * plot_h

    baseline_y = y_of(0)

    grid_lines = []
    tick_count = 4
    for i in range(tick_count + 1):
        gy = pad_t + plot_h * i / tick_count
        val = y_max - (y_max - y_min) * i / tick_count
        grid_lines.append(
            f'<line class="viz-grid" x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" y2="{gy:.1f}" />'
            f'<text class="viz-axis-label" x="{pad_l - 8}" y="{gy + 4:.1f}" text-anchor="end">{val:,.0f}</text>'
        )

    bar_els = []
    for i, (label, v) in enumerate(bars):
        cx = pad_l + slot_w * (i + 0.5)
        bx = cx - bar_w / 2
        top = y_of(max(v, 0))
        bot = y_of(min(v, 0))
        bar_h = max(bot - top, 1)
        bar_els.append(
            f'<rect class="viz-bar" x="{bx:.1f}" y="{top:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" rx="4" '
            f'data-label="{html.escape(label)}" data-value="{v:.2f}" data-unit="{html.escape(unit)}" '
            f'tabindex="0" />'
        )
        bar_els.append(
            f'<text class="viz-axis-label" x="{cx:.1f}" y="{height - 6}" text-anchor="middle">{html.escape(label)}</text>'
        )

    return f"""
<div class="viz-chart-wrap" data-chart="bar">
  <svg viewBox="0 0 {width} {height}" class="viz-svg" role="img" aria-label="Μηνιαίο κέρδος μηχανής">
    {''.join(grid_lines)}
    <line class="viz-baseline" x1="{pad_l}" y1="{baseline_y:.1f}" x2="{width - pad_r}" y2="{baseline_y:.1f}" />
    {''.join(bar_els)}
  </svg>
  <div class="viz-tooltip" hidden></div>
</div>
"""


SERIES_VARS = ["--series-1", "--series-2", "--series-3", "--series-4", "--series-5"]


def _svg_multiline_chart(
    series: list[tuple[str, list[tuple[str, float]]]],
    width=1200,
    height=320,
    indexed: bool = True,
    fill_between: tuple[str, str] | None = None,
    unit: str = "",
) -> str:
    """Multiple series sharing one x-axis of labels and one y-axis.

    When ``indexed`` (the default), every series is rescaled to 100 at its
    first point, so series with unrelated units/scales can share an axis.
    Set ``indexed=False`` when the series already share a unit (e.g. two
    prices in €/MWh) and the actual values matter. ``fill_between`` shades
    the area between two named series (e.g. a headroom/cushion band).
    """
    if not series or not series[0][1]:
        return '<p class="viz-empty">Δεν υπάρχουν ακόμα δεδομένα.</p>'

    labels = [label for label, _ in series[0][1]]
    n = len(labels)

    pad_l, pad_r, pad_t, pad_b = 48, 16, 16, 44
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    if indexed:
        plotted_series = []
        for name, points in series:
            base = points[0][1] or 1
            plotted_series.append((name, [(label, v / base * 100) for label, v in points]))
    else:
        plotted_series = series

    all_values = [v for _, points in plotted_series for _, v in points]
    y_min, y_max = min(all_values), max(all_values)
    if y_min == y_max:
        y_min -= 1
        y_max += 1
    y_pad = (y_max - y_min) * 0.10
    y_min -= y_pad
    y_max += y_pad

    def x_of(i: int) -> float:
        return pad_l + (plot_w * i / (n - 1) if n > 1 else plot_w / 2)

    def y_of(v: float) -> float:
        return pad_t + plot_h - (v - y_min) / (y_max - y_min) * plot_h

    grid_lines = []
    tick_count = 4
    for i in range(tick_count + 1):
        gy = pad_t + plot_h * i / tick_count
        val = y_max - (y_max - y_min) * i / tick_count
        grid_lines.append(
            f'<line class="viz-grid" x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" y2="{gy:.1f}" />'
            f'<text class="viz-axis-label" x="{pad_l - 8}" y="{gy + 4:.1f}" text-anchor="end">{val:,.0f}</text>'
        )
    if indexed:
        baseline_y = y_of(100)
        grid_lines.append(
            f'<line class="viz-baseline" x1="{pad_l}" y1="{baseline_y:.1f}" x2="{width - pad_r}" y2="{baseline_y:.1f}" stroke-dasharray="3,3" />'
        )

    x_labels = []
    label_idx = list(range(n)) if n <= 9 else sorted(set([0, n // 4, n // 2, (3 * n) // 4, n - 1]))
    for i in label_idx:
        anchor = "start" if i == 0 else "end" if i == n - 1 else "middle"
        x_labels.append(
            f'<text class="viz-axis-label" x="{x_of(i):.1f}" y="{height - pad_b + 20}" text-anchor="{anchor}">'
            f'{html.escape(labels[i])}</text>'
        )

    coords_by_name = {}
    for name, points in plotted_series:
        coords_by_name[name] = [(x_of(i), y_of(v)) for i, (_, v) in enumerate(points)]

    fill_el = ""
    if fill_between and all(name in coords_by_name for name in fill_between):
        top_name, bottom_name = fill_between
        top = coords_by_name[top_name]
        bottom = coords_by_name[bottom_name]
        forward = " L ".join(f"{x:.1f},{y:.1f}" for x, y in top)
        backward = " L ".join(f"{x:.1f},{y:.1f}" for x, y in reversed(bottom))
        fill_el = f'<path class="viz-band" d="M {forward} L {backward} Z" />'

    paths = [fill_el]
    legend_items = []
    per_month = [{"label": labels[i]} for i in range(n)]
    for s_idx, (name, points) in enumerate(plotted_series):
        var = SERIES_VARS[s_idx % len(SERIES_VARS)]
        coords = coords_by_name[name]
        path_d = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
        paths.append(f'<path class="viz-line" style="stroke:var({var})" d="{path_d}" />')
        ex, ey = coords[-1]
        paths.append(f'<circle class="viz-end-dot" style="fill:var({var})" cx="{ex:.1f}" cy="{ey:.1f}" r="4" />')
        legend_items.append(
            f'<span class="viz-legend-item"><span class="viz-legend-key" style="background:var({var})"></span>{html.escape(name)}</span>'
        )
        for i, (_, v) in enumerate(points):
            per_month[i][name] = round(v, 1)

    x_positions = [x_of(i) for i in range(n)]
    data_json = json.dumps([{"x": x_positions[i], **per_month[i]} for i in range(n)])
    series_names = json.dumps([name for name, _ in plotted_series])

    axis_label = "Δείκτης 100 = πρώτος μήνας" if indexed else unit
    return f"""
<div class="viz-chart-wrap" data-chart="multiline" data-unit="{html.escape(unit)}">
  <div class="viz-legend">{''.join(legend_items)}</div>
  <svg viewBox="0 0 {width} {height}" class="viz-svg" role="img" aria-label="{html.escape(axis_label)}, {', '.join(html.escape(name) for name, _ in series)}">
    {''.join(grid_lines)}
    {''.join(paths)}
    {''.join(x_labels)}
    <rect class="viz-hit-rect" x="{pad_l}" y="{pad_t}" width="{plot_w}" height="{plot_h}"
          data-points='{data_json}' data-series='{series_names}' />
  </svg>
  <div class="viz-tooltip" hidden></div>
  <div class="viz-crosshair" hidden></div>
</div>
"""


def _linreg(xs: list[float], ys: list[float]) -> tuple[float, float]:
    n = len(xs)
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var = sum((x - mean_x) ** 2 for x in xs)
    slope = cov / var if var else 0.0
    intercept = mean_y - slope * mean_x
    return slope, intercept


def _svg_scatter_chart(
    points: list[tuple[str, float, float]], x_unit: str, y_unit: str, r: float | None, width=1200, height=320
) -> str:
    """points: list of (label, x, y). Draws a trendline and an r annotation if r is given."""
    if not points:
        return '<p class="viz-empty">Δεν υπάρχουν αρκετά δεδομένα για συσχέτιση.</p>'

    pad_l, pad_r, pad_t, pad_b = 56, 16, 16, 32
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    xs = [x for _, x, _ in points]
    ys = [y for _, _, y in points]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    if x_min == x_max:
        x_min -= 1
        x_max += 1
    if y_min == y_max:
        y_min -= 1
        y_max += 1
    x_pad = (x_max - x_min) * 0.10
    y_pad = (y_max - y_min) * 0.10
    x_min, x_max = x_min - x_pad, x_max + x_pad
    y_min, y_max = y_min - y_pad, y_max + y_pad

    def x_of(v: float) -> float:
        return pad_l + (v - x_min) / (x_max - x_min) * plot_w

    def y_of(v: float) -> float:
        return pad_t + plot_h - (v - y_min) / (y_max - y_min) * plot_h

    grid_lines = []
    tick_count = 4
    for i in range(tick_count + 1):
        gy = pad_t + plot_h * i / tick_count
        val = y_max - (y_max - y_min) * i / tick_count
        grid_lines.append(
            f'<line class="viz-grid" x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" y2="{gy:.1f}" />'
            f'<text class="viz-axis-label" x="{pad_l - 8}" y="{gy + 4:.1f}" text-anchor="end">{val:,.0f}</text>'
        )
    for i in range(tick_count + 1):
        gx = pad_l + plot_w * i / tick_count
        val = x_min + (x_max - x_min) * i / tick_count
        grid_lines.append(
            f'<text class="viz-axis-label" x="{gx:.1f}" y="{height - 8}" text-anchor="middle">{val:,.0f}</text>'
        )

    trend = ""
    if len(points) >= 2:
        slope, intercept = _linreg(xs, ys)
        tx1, tx2 = x_min, x_max
        ty1, ty2 = slope * tx1 + intercept, slope * tx2 + intercept
        trend = (
            f'<line class="viz-trendline" x1="{x_of(tx1):.1f}" y1="{y_of(ty1):.1f}" '
            f'x2="{x_of(tx2):.1f}" y2="{y_of(ty2):.1f}" />'
        )

    dots = []
    for label, x, y in points:
        cx, cy = x_of(x), y_of(y)
        dots.append(
            f'<circle class="viz-scatter-dot" cx="{cx:.1f}" cy="{cy:.1f}" r="6" '
            f'data-label="{html.escape(label)}" data-x="{x:.2f}" data-y="{y:.2f}" '
            f'data-x-unit="{html.escape(x_unit)}" data-y-unit="{html.escape(y_unit)}" tabindex="0" />'
        )

    r_label = f'<text class="viz-r-label" x="{width - pad_r}" y="{pad_t + 14}" text-anchor="end">r = {r:.2f}</text>' if r is not None else ""

    return f"""
<div class="viz-chart-wrap" data-chart="scatter">
  <svg viewBox="0 0 {width} {height}" class="viz-svg" role="img" aria-label="Συσχέτιση {html.escape(x_unit)} - {html.escape(y_unit)}">
    {''.join(grid_lines)}
    {trend}
    {''.join(dots)}
    {r_label}
  </svg>
  <div class="viz-tooltip" hidden></div>
</div>
"""


def _table_html(headers: list[str], rows: list[list[str]], hidden: bool = True) -> str:
    thead = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    trs = []
    for row in rows:
        tds = "".join(f"<td>{html.escape(str(c))}</td>" for c in row)
        trs.append(f"<tr>{tds}</tr>")
    hidden_attr = " hidden" if hidden else ""
    return f'<table class="viz-table"{hidden_attr}><thead><tr>{thead}</tr></thead><tbody>{"".join(trs)}</tbody></table>'


def _stat_tile(label: str, value: str, sublabel: str = "") -> str:
    sub = f'<div class="viz-stat-sub">{html.escape(sublabel)}</div>' if sublabel else ""
    return f"""
<div class="viz-stat-tile">
  <div class="viz-stat-label">{html.escape(label)}</div>
  <div class="viz-stat-value">{html.escape(value)}</div>
  {sub}
</div>
"""


CSS = """
:root { color-scheme: light; }
.viz-root {
  --surface-1: #fcfcfb; --page: #f9f9f7;
  --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #898781;
  --grid: #e1e0d9; --baseline: #c3c2b7; --border: rgba(11,11,11,0.10);
  --series-1: #2a78d6; --series-2: #eb6834; --series-3: #1baf7a; --series-4: #eda100; --series-5: #e87ba4;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) .viz-root {
    color-scheme: dark;
    --surface-1: #1a1a19; --page: #0d0d0d;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #898781;
    --grid: #2c2c2a; --baseline: #383835; --border: rgba(255,255,255,0.10);
    --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70; --series-4: #c98500; --series-5: #d55181;
  }
}
:root[data-theme="dark"] .viz-root {
  color-scheme: dark;
  --surface-1: #1a1a19; --page: #0d0d0d;
  --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #898781;
  --grid: #2c2c2a; --baseline: #383835; --border: rgba(255,255,255,0.10);
  --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70; --series-4: #c98500; --series-5: #d55181;
}
.viz-root {
  background: var(--page);
  color: var(--text-primary);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  min-height: 100vh;
  padding: 24px clamp(16px, 4vw, 56px) 48px;
}
.viz-shell { max-width: 1800px; margin: 0 auto; }
.viz-header { display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 8px; margin-bottom: 20px; }
.viz-title { font-size: 22px; font-weight: 600; margin: 0; }
.viz-updated { font-size: 13px; color: var(--text-muted); }
.viz-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 24px; }
.viz-stat-tile { background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }
.viz-stat-label { font-size: 12px; color: var(--text-secondary); }
.viz-stat-value { font-size: 24px; font-weight: 600; margin-top: 4px; }
.viz-stat-sub { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
.viz-card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 16px 16px 8px; margin-bottom: 24px; position: relative; }
.viz-card-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.viz-card-title { font-size: 15px; font-weight: 600; margin: 0; }
.viz-toggle { font: inherit; font-size: 12px; color: var(--text-secondary); background: transparent; border: 1px solid var(--border); border-radius: 6px; padding: 4px 10px; cursor: pointer; }
.viz-toggle:hover { color: var(--text-primary); }
.viz-chart-wrap { position: relative; }
.viz-svg { width: 100%; height: auto; display: block; }
.viz-grid { stroke: var(--grid); stroke-width: 1; }
.viz-baseline { stroke: var(--baseline); stroke-width: 1; }
.viz-band { fill: var(--series-1); opacity: 0.08; stroke: none; }
.viz-axis-label { fill: var(--text-muted); font-size: 11px; }
.viz-line { fill: none; stroke: var(--series-1); stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
.viz-area { fill: var(--series-1); opacity: 0.10; }
.viz-end-dot { fill: var(--series-1); stroke: var(--surface-1); stroke-width: 2; }
.viz-bar { fill: var(--series-1); cursor: pointer; }
.viz-bar:hover, .viz-bar:focus { fill: var(--series-2); outline: none; }
.viz-hit-rect { fill: transparent; }
.viz-crosshair { position: absolute; top: 0; width: 1px; background: var(--baseline); pointer-events: none; }
.viz-tooltip { position: absolute; pointer-events: none; background: var(--surface-1); border: 1px solid var(--border); border-radius: 8px; padding: 6px 10px; font-size: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.12); white-space: nowrap; }
.viz-tooltip strong { font-size: 13px; }
.viz-table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 8px; }
.viz-table th, .viz-table td { text-align: right; padding: 6px 8px; border-bottom: 1px solid var(--grid); font-variant-numeric: tabular-nums; }
.viz-table th:first-child, .viz-table td:first-child { text-align: left; font-variant-numeric: normal; }
.viz-empty { color: var(--text-muted); font-size: 13px; padding: 24px 0; text-align: center; }
.viz-footer { font-size: 12px; color: var(--text-muted); margin-top: 8px; }
.viz-legend { display: flex; flex-wrap: wrap; gap: 4px 16px; margin-bottom: 4px; }
.viz-legend-item { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-secondary); }
.viz-legend-key { width: 12px; height: 2px; border-radius: 1px; display: inline-block; }
.viz-scatter-dot { fill: var(--series-1); stroke: var(--surface-1); stroke-width: 2; cursor: pointer; }
.viz-scatter-dot:hover, .viz-scatter-dot:focus { fill: var(--series-2); outline: none; }
.viz-trendline { stroke: var(--text-muted); stroke-width: 1.5; stroke-dasharray: 5,4; }
.viz-r-label { fill: var(--text-secondary); font-size: 12px; font-weight: 600; }
.viz-summary-table td:first-child, .viz-summary-table th:first-child { text-align: left; }
.viz-section-title { font-size: 18px; font-weight: 600; margin: 8px 0 12px; }
.viz-summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }
.viz-summary-grid .viz-table { margin-top: 0; }
[hidden] { display: none !important; }
"""

JS = """
function initLineChart(wrap) {
  const svg = wrap.querySelector('svg');
  const hit = wrap.querySelector('.viz-hit-rect');
  const tooltip = wrap.querySelector('.viz-tooltip');
  const crosshair = wrap.querySelector('.viz-crosshair');
  if (!hit) return;
  const points = JSON.parse(hit.getAttribute('data-points'));
  function nearest(mx) {
    let best = points[0], bestDist = Infinity;
    for (const p of points) {
      const d = Math.abs(p.x - mx);
      if (d < bestDist) { best = p; bestDist = d; }
    }
    return best;
  }
  function onMove(evt) {
    const rect = svg.getBoundingClientRect();
    const scaleX = svg.viewBox.baseVal.width / rect.width;
    const mx = (evt.clientX - rect.left) * scaleX;
    const p = nearest(mx);
    const wrapRect = wrap.getBoundingClientRect();
    const px = (p.x / svg.viewBox.baseVal.width) * wrapRect.width;
    crosshair.style.left = px + 'px';
    crosshair.style.height = wrapRect.height + 'px';
    crosshair.hidden = false;
    tooltip.innerHTML = '';
    const strong = document.createElement('strong');
    strong.textContent = p.value.toFixed(2) + ' €/MWh';
    const div = document.createElement('div');
    div.textContent = p.date;
    tooltip.appendChild(strong);
    tooltip.appendChild(div);
    tooltip.hidden = false;
    let left = px + 12;
    if (left + 140 > wrapRect.width) left = px - 152;
    tooltip.style.left = left + 'px';
    tooltip.style.top = '8px';
  }
  function onLeave() { tooltip.hidden = true; crosshair.hidden = true; }
  hit.addEventListener('pointermove', onMove);
  hit.addEventListener('pointerleave', onLeave);
}

function initBarChart(wrap) {
  const tooltip = wrap.querySelector('.viz-tooltip');
  const bars = wrap.querySelectorAll('.viz-bar');
  bars.forEach(bar => {
    function show(evt) {
      const wrapRect = wrap.getBoundingClientRect();
      const barRect = bar.getBoundingClientRect();
      tooltip.innerHTML = '';
      const strong = document.createElement('strong');
      const value = parseFloat(bar.getAttribute('data-value'));
      const unit = bar.getAttribute('data-unit');
      strong.textContent = value.toLocaleString('el-GR', {maximumFractionDigits: 0}) + ' ' + unit;
      const div = document.createElement('div');
      div.textContent = bar.getAttribute('data-label');
      tooltip.appendChild(strong);
      tooltip.appendChild(div);
      tooltip.hidden = false;
      let left = barRect.left - wrapRect.left;
      tooltip.style.left = left + 'px';
      tooltip.style.top = '4px';
    }
    bar.addEventListener('pointerenter', show);
    bar.addEventListener('focus', show);
    bar.addEventListener('pointerleave', () => tooltip.hidden = true);
    bar.addEventListener('blur', () => tooltip.hidden = true);
  });
}

function initMultiLineChart(wrap) {
  const svg = wrap.querySelector('svg');
  const hit = wrap.querySelector('.viz-hit-rect');
  const tooltip = wrap.querySelector('.viz-tooltip');
  const crosshair = wrap.querySelector('.viz-crosshair');
  if (!hit) return;
  const points = JSON.parse(hit.getAttribute('data-points'));
  const names = JSON.parse(hit.getAttribute('data-series'));
  const unit = wrap.getAttribute('data-unit') || '';
  function nearest(mx) {
    let best = points[0], bestDist = Infinity;
    for (const p of points) {
      const d = Math.abs(p.x - mx);
      if (d < bestDist) { best = p; bestDist = d; }
    }
    return best;
  }
  function onMove(evt) {
    const rect = svg.getBoundingClientRect();
    const scaleX = svg.viewBox.baseVal.width / rect.width;
    const mx = (evt.clientX - rect.left) * scaleX;
    const p = nearest(mx);
    const wrapRect = wrap.getBoundingClientRect();
    const px = (p.x / svg.viewBox.baseVal.width) * wrapRect.width;
    crosshair.style.left = px + 'px';
    crosshair.style.height = wrapRect.height + 'px';
    crosshair.hidden = false;
    tooltip.innerHTML = '';
    const head = document.createElement('div');
    head.appendChild(Object.assign(document.createElement('strong'), {textContent: p.label}));
    tooltip.appendChild(head);
    names.forEach((name, i) => {
      const row = document.createElement('div');
      row.textContent = name + ': ' + p[name].toFixed(1) + (unit ? ' ' + unit : '');
      tooltip.appendChild(row);
    });
    tooltip.hidden = false;
    let left = px + 12;
    if (left + 160 > wrapRect.width) left = px - 172;
    tooltip.style.left = left + 'px';
    tooltip.style.top = '8px';
  }
  function onLeave() { tooltip.hidden = true; crosshair.hidden = true; }
  hit.addEventListener('pointermove', onMove);
  hit.addEventListener('pointerleave', onLeave);
}

function initScatterChart(wrap) {
  const tooltip = wrap.querySelector('.viz-tooltip');
  const dots = wrap.querySelectorAll('.viz-scatter-dot');
  dots.forEach(dot => {
    function show() {
      const wrapRect = wrap.getBoundingClientRect();
      const dotRect = dot.getBoundingClientRect();
      tooltip.innerHTML = '';
      const strong = document.createElement('strong');
      const x = parseFloat(dot.getAttribute('data-x'));
      const y = parseFloat(dot.getAttribute('data-y'));
      strong.textContent = dot.getAttribute('data-label');
      const rowX = document.createElement('div');
      rowX.textContent = dot.getAttribute('data-x-unit') + ': ' + x.toFixed(1);
      const rowY = document.createElement('div');
      rowY.textContent = dot.getAttribute('data-y-unit') + ': ' + y.toLocaleString('el-GR', {maximumFractionDigits: 0});
      tooltip.appendChild(strong);
      tooltip.appendChild(rowX);
      tooltip.appendChild(rowY);
      tooltip.hidden = false;
      tooltip.style.left = (dotRect.left - wrapRect.left + 10) + 'px';
      tooltip.style.top = (dotRect.top - wrapRect.top - 8) + 'px';
    }
    dot.addEventListener('pointerenter', show);
    dot.addEventListener('focus', show);
    dot.addEventListener('pointerleave', () => tooltip.hidden = true);
    dot.addEventListener('blur', () => tooltip.hidden = true);
  });
}

document.querySelectorAll('[data-chart="line"]').forEach(initLineChart);
document.querySelectorAll('[data-chart="bar"]').forEach(initBarChart);
document.querySelectorAll('[data-chart="multiline"]').forEach(initMultiLineChart);
document.querySelectorAll('[data-chart="scatter"]').forEach(initScatterChart);

document.querySelectorAll('.viz-toggle').forEach(btn => {
  btn.addEventListener('click', () => {
    const card = btn.closest('.viz-card');
    const chart = card.querySelector('.viz-chart-wrap');
    const table = card.querySelector('.viz-table');
    if (!chart || !table) return;
    const nowShowingTable = chart.hidden;
    chart.hidden = !nowShowingTable;
    table.hidden = nowShowingTable;
    btn.textContent = nowShowingTable ? 'Πίνακας' : 'Γράφημα';
  });
});
"""


def build_dashboard_html(mcp_df: pd.DataFrame, monthly_prices: pd.DataFrame) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if mcp_df.empty:
        daily = pd.DataFrame(columns=["date_str", "mcp"])
    else:
        daily = _daily_avg_mcp(mcp_df)

    profit_df, skipped_months = compute_monthly_profit(mcp_df, monthly_prices) if not mcp_df.empty else (
        pd.DataFrame(columns=["month", "hours", "avg_margin_eur_per_mwh", "profit_eur"]), []
    )

    incomplete_days = find_incomplete_days(mcp_df) if not mcp_df.empty else []

    latest_mcp = daily["mcp"].iloc[-1] if not daily.empty else None
    latest_date = daily["date_str"].iloc[-1] if not daily.empty else "—"
    total_profit = profit_df["profit_eur"].sum() if not profit_df.empty else None
    avg_margin = profit_df["avg_margin_eur_per_mwh"].mean() if not profit_df.empty else None

    stats = [
        _stat_tile("Τελευταία ημερήσια μέση MCP", f"{latest_mcp:,.2f} €/MWh" if latest_mcp is not None else "—", latest_date),
        _stat_tile("Συνολικό κέρδος (πλήρεις μήνες)", f"{total_profit:,.0f} €" if total_profit is not None else "—", f"{len(profit_df)} μήνες"),
        _stat_tile("Μέσο margin", f"{avg_margin:,.2f} €/MWh" if avg_margin is not None else "—", f"1 MW, {PLANT_EFFICIENCY:.0%} απόδοση"),
        _stat_tile("Ελλιπείς ημέρες", str(len(incomplete_days)), "λιγότερες από 24 εγγραφές"),
    ]

    line_points = list(zip(daily["date_str"], daily["mcp"])) if not daily.empty else []
    line_chart = _svg_line_chart(line_points)
    line_table = _table_html(
        ["Ημερομηνία", "Μέση MCP (€/MWh)"],
        [[d, f"{v:.2f}"] for d, v in line_points],
    )

    bar_points = [(_month_label(m), v) for m, v in zip(profit_df["month"], profit_df["profit_eur"])] if not profit_df.empty else []
    bar_chart = _svg_bar_chart(bar_points, unit="€")
    bar_table = _table_html(
        ["Μήνας", "Ώρες", "Μέσο margin (€/MWh)", "Κέρδος (€)"],
        [
            [_month_label(row.month), int(row.hours), f"{row.avg_margin_eur_per_mwh:.2f}", f"{row.profit_eur:,.0f}"]
            for row in profit_df.itertuples()
        ] if not profit_df.empty else [],
    )

    skipped_note = ""
    if skipped_months:
        items = "".join(f"<li>{html.escape(s)}</li>" for s in skipped_months)
        skipped_note = f'<p class="viz-footer">Μήνες εκτός γραφήματος κέρδους (ελλιπείς τιμές ΤΑ/ΕΤΑ/TTF): <ul>{items}</ul></p>'

    summary, _ = monthly_summary(mcp_df, monthly_prices) if not mcp_df.empty else (pd.DataFrame(), [])

    trend_chart = ""
    trend_table = ""
    scatter_chart = ""
    scatter_table = ""
    breakeven_chart = ""
    breakeven_table = ""
    revenue_scatter_chart = ""
    revenue_scatter_table = ""
    averages_table = ""
    correlations_table = ""
    if not summary.empty:
        month_labels = [_month_label(m) for m in summary["month"]]
        trend_cols = ["avg_mcp", "ta", "eta", "ttf", "profit_eur"]
        trend_series = [(METRIC_LABELS[col], list(zip(month_labels, summary[col]))) for col in trend_cols]
        trend_chart = _svg_multiline_chart(trend_series)
        trend_table = _table_html(
            ["Μήνας"] + [METRIC_LABELS[c] for c in trend_cols],
            [
                [month_labels[i]] + [f"{row[c]:,.1f}" for c in trend_cols]
                for i, (_, row) in enumerate(summary.iterrows())
            ],
        )

        scatter_points = list(zip(month_labels, summary["ttf"], summary["profit_eur"]))
        correlations = compute_correlations(summary)
        ttf_profit_r = next((c["r"] for c in correlations if c["label"] == "TTF ↔ Κέρδος"), None)
        scatter_chart = _svg_scatter_chart(scatter_points, "TTF €/MWh", "Κέρδος €", ttf_profit_r)
        scatter_table = _table_html(
            ["Μήνας", "TTF (€/MWh)", "Κέρδος (€)"],
            [[label, f"{x:.2f}", f"{y:,.0f}"] for label, x, y in scatter_points],
        )

        breakeven_series = [
            (METRIC_LABELS["ttf"], list(zip(month_labels, summary["ttf"]))),
            (METRIC_LABELS["breakeven_ttf"], list(zip(month_labels, summary["breakeven_ttf"]))),
        ]
        breakeven_chart = _svg_multiline_chart(
            breakeven_series, indexed=False, unit="€/MWh",
            fill_between=(METRIC_LABELS["breakeven_ttf"], METRIC_LABELS["ttf"]),
        )
        breakeven_table = _table_html(
            ["Μήνας", "TTF (€/MWh)", "Breakeven TTF (€/MWh)", "Περιθώριο ασφαλείας (€/MWh)"],
            [
                [month_labels[i], f"{row.ttf:.2f}", f"{row.breakeven_ttf:.2f}", f"{row.breakeven_ttf - row.ttf:+.2f}"]
                for i, row in enumerate(summary.itertuples())
            ],
        )

        revenue_scatter_points = list(zip(month_labels, summary["ttf"], summary["revenue_side"]))
        ttf_revenue_r = next((c["r"] for c in correlations if c["label"] == "TTF ↔ (MCP+ΤΑ-ΕΤΑ)"), None)
        revenue_scatter_chart = _svg_scatter_chart(
            revenue_scatter_points, "TTF €/MWh", "MCP+ΤΑ-ΕΤΑ €/MWh", ttf_revenue_r
        )
        revenue_scatter_table = _table_html(
            ["Μήνας", "TTF (€/MWh)", "MCP+ΤΑ-ΕΤΑ (€/MWh)"],
            [[label, f"{x:.2f}", f"{y:.2f}"] for label, x, y in revenue_scatter_points],
        )

        averages = column_averages(summary)
        averages_table = _table_html(
            ["Μέγεθος", "Μέσος όρος"],
            [[METRIC_LABELS.get(k, k), f"{v:,.2f} {METRIC_UNITS.get(k, '')}"] for k, v in averages.items()],
            hidden=False,
        )
        correlations_table = _table_html(
            ["Ζεύγος", "r (Pearson)", "n"],
            [[c["label"], f"{c['r']:.2f}", c["n"]] for c in correlations],
            hidden=False,
        )

    n_months_analysis = len(summary) if not summary.empty else 0

    return f"""<!doctype html>
<html lang="el">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>EnEx DAM MCP — Dashboard</title>
<style>{CSS}</style>
</head>
<body>
<div class="viz-root">
  <div class="viz-shell">
    <div class="viz-header">
      <h1 class="viz-title">EnEx DAM MCP — Dashboard</h1>
      <div class="viz-updated">Ενημερώθηκε: {generated_at}</div>
    </div>

    <div class="viz-stats">{''.join(stats)}</div>

    <div class="viz-card">
      <div class="viz-card-head">
        <h2 class="viz-card-title">Ημερήσια μέση τιμή MCP</h2>
        <button class="viz-toggle" type="button">Πίνακας</button>
      </div>
      {line_chart}
      {line_table}
    </div>

    <div class="viz-card">
      <div class="viz-card-head">
        <h2 class="viz-card-title">Μηνιαίο κέρδος μηχανής</h2>
        <button class="viz-toggle" type="button">Πίνακας</button>
      </div>
      {bar_chart}
      {bar_table}
      {skipped_note}
    </div>

    <h2 class="viz-section-title">Ανάλυση ({n_months_analysis} πλήρεις μήνες)</h2>

    <div class="viz-card">
      <div class="viz-card-head">
        <h2 class="viz-card-title">Τάσεις (δείκτης 100 = πρώτος μήνας)</h2>
        <button class="viz-toggle" type="button">Πίνακας</button>
      </div>
      {trend_chart or '<p class="viz-empty">Δεν υπάρχουν ακόμα πλήρεις μήνες.</p>'}
      {trend_table}
    </div>

    <div class="viz-card">
      <div class="viz-card-head">
        <h2 class="viz-card-title">TTF vs Κέρδος</h2>
        <button class="viz-toggle" type="button">Πίνακας</button>
      </div>
      {scatter_chart or '<p class="viz-empty">Δεν υπάρχουν ακόμα πλήρεις μήνες.</p>'}
      {scatter_table}
    </div>

    <div class="viz-card">
      <div class="viz-card-head">
        <h2 class="viz-card-title">Breakeven TTF</h2>
        <button class="viz-toggle" type="button">Πίνακας</button>
      </div>
      {breakeven_chart or '<p class="viz-empty">Δεν υπάρχουν ακόμα πλήρεις μήνες.</p>'}
      {breakeven_table}
      <p class="viz-footer">Breakeven TTF = (MCP + ΤΑ − ΕΤΑ) × {PLANT_EFFICIENCY:.2f} — η τιμή αερίου στην οποία το margin μηδενίζεται. Η σκιασμένη περιοχή είναι το περιθώριο ασφαλείας· όσο πιο κοντά οι δύο γραμμές, τόσο πιο ευάλωτο το κέρδος σε άνοδο του TTF.</p>
    </div>

    <div class="viz-card">
      <div class="viz-card-head">
        <h2 class="viz-card-title">TTF vs (MCP+ΤΑ-ΕΤΑ)</h2>
        <button class="viz-toggle" type="button">Πίνακας</button>
      </div>
      {revenue_scatter_chart or '<p class="viz-empty">Δεν υπάρχουν ακόμα πλήρεις μήνες.</p>'}
      {revenue_scatter_table}
    </div>

    <div class="viz-card">
      <div class="viz-card-head">
        <h2 class="viz-card-title">Μέσοι όροι &amp; συσχετίσεις</h2>
      </div>
      <div class="viz-summary-grid">
        {averages_table or '<p class="viz-empty">—</p>'}
        {correlations_table or '<p class="viz-empty">—</p>'}
      </div>
      <p class="viz-footer">Το ΜΤΦΑ συσχετίζεται σχεδόν τέλεια με το TTF (r ≈ 1) — ουσιαστικά το ίδιο σήμα, διαφορετική κλιμάκωση.</p>
    </div>

    <p class="viz-footer">Τύπος: MCP + ΤΑ − ΕΤΑ − (TTF / {PLANT_EFFICIENCY:.2f}), μονάδα {PLANT_CAPACITY_MW:.0f} MW. Πηγή: <a href="https://github.com/VaGlar/EnEx-WebScraping">EnEx-WebScraping</a>.</p>
  </div>
</div>
<script>{JS}</script>
</body>
</html>
"""
