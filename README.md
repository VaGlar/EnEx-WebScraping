# EnEx DAM MCP Collector

Automated collection, logging and completeness checking of hourly MCP
(Marginal Clearing Price) values from the daily DAM (Day-Ahead Market)
files published by EnEx Group.

The project started as a set of Google Colab notebooks and has since been
converted into a regular Python package (`enex_dam`) that runs either
locally or via GitHub Actions, with no dependency on Google Colab/Drive.

## 📁 Structure

```
enex_dam/
  config.py        # URL template, paths, retry/backoff, known exceptions (DST)
  dam.py            # download + parse a single day's DAM file
  storage.py        # load/merge/save the dataset as CSV
  completeness.py   # finds missing/incomplete dates
  economics.py       # monthly plant profit calculation (see below)
  dashboard.py        # generates the static HTML dashboard (see below)
  logging_config.py # shared logging setup (file + console)
  scripts/
    bulk_download.py  # bulk download for a date range
    daily_update.py   # fetch a single day (default: today)
    check_missing.py  # dataset completeness check
    manual_insert.py  # interactive entry of specific dates
    compute_profit.py # computes & prints monthly profit
    build_dashboard.py # generates docs/index.html
data/
  mcp_full.csv       # the dataset (date, hour, mcp), updated automatically
  monthly_prices.csv # monthly TA/ETA/TTF prices (updated manually)
docs/
  index.html          # the dashboard, updated automatically, served by GitHub Pages
tests/               # pytest unit tests (no real network calls)
.github/workflows/
  daily_update.yml   # daily cron that runs daily_update + commit
  backfill.yml       # manual (workflow_dispatch) backfill for a date range
```

## ▶️ Usage

```bash
pip install -r requirements.txt

# Initial bulk download (backfill) - defaults to DATA_START_DATE through today
python -m enex_dam.scripts.bulk_download --start 2026-01-01 --end 2026-08-19

# Daily update (today's date)
python -m enex_dam.scripts.daily_update

# Completeness check
python -m enex_dam.scripts.check_missing

# Manually insert specific dates
python -m enex_dam.scripts.manual_insert

# Compute monthly plant profit
python -m enex_dam.scripts.compute_profit

# Generate/update the dashboard (docs/index.html)
python -m enex_dam.scripts.build_dashboard
```

For development/tests:

```bash
pip install -r requirements-dev.txt
pytest
```

## 🤖 Automation

The `.github/workflows/daily_update.yml` workflow runs daily (cron, UTC
time - see the comment in the file for the conversion to Greek time),
downloads the day's prices, checks completeness, and commits the updated
`data/mcp_full.csv` back to the repo. It can also be run manually from the
**Actions** tab (`workflow_dispatch`).

For the initial historical backfill (before the daily cron was enabled)
there's a separate `backfill.yml` workflow: **Actions → Backfill DAM MCP
data → Run workflow**, with optional `start`/`end` fields (default:
`2026-01-01` through today). It runs on GitHub's runner, so nothing needs
to run locally.

## 📄 Logging

Logs are written locally to `logs/mcp_log.txt` (not committed to the repo -
see the run history in the GitHub Actions run log).

## 💶 Monthly plant profit

The installation is a 1 MW natural gas unit, 43% efficiency
(`PLANT_CAPACITY_MW`, `PLANT_EFFICIENCY` in `enex_dam/config.py`). Per hour:

```
margin (€/MWh electricity) = MCP + TA - ETA - (TTF / 0.43)
```

where TA (Reference Price), ETA (Special RES Levy) and TTF (natural gas
price, €/MWh gas) are monthly constants - filled in manually in
`data/monthly_prices.csv` (columns `month,ta,eta,ttf,mtfa`). TTF is
divided by the efficiency to convert it into a fuel cost per MWh of
electricity. The `mtfa` column (Average Natural Gas Price) doesn't feed
into the formula - it's kept only for comparison/correlation with TTF on
the dashboard (see below - it's nearly identical to TTF, r ≈ 1).

Monthly profit multiplies the average margin by the hours in the month,
the capacity (1 MW), and an assumed availability factor of 350/365 (the
plant is assumed to run 24h/day, 350 days/year - `AVAILABILITY_FACTOR` in
config.py). No other operating cost (OPEX) is subtracted for now, so
"plant profit" = the revenue from this spread.

`python -m enex_dam.scripts.compute_profit` prints the monthly profit
table (hours, average margin €/MWh, profit €) and optionally saves it with
`--out FILE.csv`. If a month is missing from `monthly_prices.csv`, the
script stops with a clear error message instead of computing a wrong number.

## 📊 Dashboard

`python -m enex_dam.scripts.build_dashboard` generates a self-contained
static HTML file (`docs/index.html`, no external assets/CDN) with:
- stat tiles (latest average MCP, total profit, average margin, missing days)
- daily average MCP price chart (line chart, hover tooltip + crosshair)
- monthly plant profit chart (bar chart, hover tooltip)
- an **Analysis** section: a trend chart of MCP/TA/ETA/TTF/Profit (indexed
  to 100 at the first month, so differently-scaled quantities can share one
  chart without a second axis), TTF↔Profit and TTF↔(MCP+TA-ETA) scatter
  plots with a trendline and Pearson r, a **Breakeven TTF** chart (actual
  TTF vs. the gas price at which margin hits zero, with the safety margin
  shaded), and an averages/correlations table (`enex_dam/analysis.py`)
- full page width (up to 1800px), responsive down to mobile
- chart/table toggle on every card, dark mode (`prefers-color-scheme`)

It's rebuilt automatically on every run of `daily_update.yml` and
`backfill.yml`, so `docs/index.html` always stays in sync with
`data/mcp_full.csv`.

**Enabling GitHub Pages (one-time, manual step):** in the repo, **Settings
→ Pages → Build and deployment → Source: "Deploy from a branch"**, branch
`main`, folder `/docs`, **Save**. After the first deploy, the dashboard is
available at `https://vaglar.github.io/EnEx-WebScraping/`.

## 🗓️ Data completeness

Every date is expected to have 24 hourly records, with known exceptions
for clock-change days (23 records on the spring-forward day, 25 on the
autumn one) - defined in `enex_dam/config.py`
(`EXPECTED_HOURLY_RECORD_EXCEPTIONS`).

## ✅ Features / possible extensions

- [x] Single, reusable download/parse logic (no duplication)
- [x] Retry with backoff + timeout on every HTTP request
- [x] Full logging (success/error, no hardcoded messages)
- [x] Tests with no real network calls (mocked HTTP)
- [x] Automation via GitHub Actions (no Google Drive)
- [x] Monthly plant profit calculation (MCP+TA-ETA-TTF/efficiency)
- [x] Visualization of MCP data + monthly profit (static dashboard, GitHub Pages)
- [ ] Statistical analysis (mean/variance per month, peak/off-peak)
- [ ] Alerts (e.g. Slack/email) on error or missing data
- [ ] Archiving the raw DAM xlsx files (not just the hourly averages)
