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

from .completeness import find_incomplete_days
from .economics import compute_monthly_profit
from .config import PLANT_CAPACITY_MW, PLANT_EFFICIENCY

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


def _svg_line_chart(points: list[tuple[str, float]], width=880, height=260) -> str:
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


def _svg_bar_chart(bars: list[tuple[str, float]], width=880, height=260, unit="€") -> str:
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


def _table_html(headers: list[str], rows: list[list[str]]) -> str:
    thead = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    trs = []
    for row in rows:
        tds = "".join(f"<td>{html.escape(str(c))}</td>" for c in row)
        trs.append(f"<tr>{tds}</tr>")
    return f'<table class="viz-table" hidden><thead><tr>{thead}</tr></thead><tbody>{"".join(trs)}</tbody></table>'


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
  --series-1: #2a78d6; --series-2: #eb6834;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) .viz-root {
    color-scheme: dark;
    --surface-1: #1a1a19; --page: #0d0d0d;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #898781;
    --grid: #2c2c2a; --baseline: #383835; --border: rgba(255,255,255,0.10);
    --series-1: #3987e5; --series-2: #d95926;
  }
}
:root[data-theme="dark"] .viz-root {
  color-scheme: dark;
  --surface-1: #1a1a19; --page: #0d0d0d;
  --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #898781;
  --grid: #2c2c2a; --baseline: #383835; --border: rgba(255,255,255,0.10);
  --series-1: #3987e5; --series-2: #d95926;
}
.viz-root {
  background: var(--page);
  color: var(--text-primary);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  min-height: 100vh;
  padding: 24px 16px 48px;
}
.viz-shell { max-width: 960px; margin: 0 auto; }
.viz-header { display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 8px; margin-bottom: 20px; }
.viz-title { font-size: 22px; font-weight: 600; margin: 0; }
.viz-updated { font-size: 13px; color: var(--text-muted); }
.viz-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 24px; }
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

document.querySelectorAll('[data-chart="line"]').forEach(initLineChart);
document.querySelectorAll('[data-chart="bar"]').forEach(initBarChart);

document.querySelectorAll('.viz-toggle').forEach(btn => {
  btn.addEventListener('click', () => {
    const card = btn.closest('.viz-card');
    const chart = card.querySelector('.viz-chart-wrap');
    const table = card.querySelector('.viz-table');
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

    <p class="viz-footer">Τύπος: MCP + ΤΑ − ΕΤΑ − (TTF / {PLANT_EFFICIENCY:.2f}), μονάδα {PLANT_CAPACITY_MW:.0f} MW. Πηγή: <a href="https://github.com/VaGlar/EnEx-WebScraping">EnEx-WebScraping</a>.</p>
  </div>
</div>
<script>{JS}</script>
</body>
</html>
"""
