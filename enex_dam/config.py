"""Central configuration for the EnEx DAM MCP collector."""

from pathlib import Path

# EnEx publishes one DAM results workbook per delivery day, named by date.
DAM_URL_TEMPLATE = (
    "https://www.enexgroup.gr/documents/20126/200106/"
    "{date_str}_EL-DAM_Results_EN_v01.xlsx"
)

# Earliest delivery day covered by this dataset.
DATA_START_DATE = "2025-01-01"

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
DATA_FILE = DATA_DIR / "mcp_full.csv"
LOG_DIR = REPO_ROOT / "logs"
LOG_FILE = LOG_DIR / "mcp_log.txt"

# HTTP behaviour
REQUEST_TIMEOUT_SECONDS = 30
REQUEST_RETRIES = 3
REQUEST_BACKOFF_SECONDS = 2.0
# Minimum delay between consecutive requests when looping over many dates,
# to avoid hammering the EnEx server.
BULK_REQUEST_DELAY_SECONDS = 1.0

# A full delivery day normally has 24 hourly records. Known exceptions
# (e.g. clock-change days) can be added here as {"YYYY-MM-DD": expected_count}.
EXPECTED_HOURLY_RECORD_EXCEPTIONS = {
    "2025-03-30": 23,  # DST spring-forward: clocks jump 03:00 -> 04:00
    "2025-10-26": 25,  # DST autumn-back: hour 03:00-04:00 repeats
}
