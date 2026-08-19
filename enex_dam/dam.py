"""Download and parse a single day's DAM results workbook from EnEx Group."""

from __future__ import annotations

import logging
import time
from datetime import date
from io import BytesIO

import pandas as pd
import requests

from .config import (
    DAM_URL_TEMPLATE,
    REQUEST_BACKOFF_SECONDS,
    REQUEST_RETRIES,
    REQUEST_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"DELIVERY_MTU", "MCP"}


class DamFileNotAvailable(Exception):
    """Raised when EnEx has not published a DAM file for the requested day."""


class DamFileMalformed(Exception):
    """Raised when a downloaded DAM file doesn't have the expected columns."""


def _dam_url(day: date) -> str:
    return DAM_URL_TEMPLATE.format(date_str=day.strftime("%Y%m%d"))


def _download(day: date, session: requests.Session) -> bytes:
    url = _dam_url(day)
    last_error: Exception | None = None
    for attempt in range(1, REQUEST_RETRIES + 1):
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            last_error = exc
            logger.warning(
                "Attempt %d/%d to fetch %s failed: %s", attempt, REQUEST_RETRIES, url, exc
            )
            time.sleep(REQUEST_BACKOFF_SECONDS * attempt)
            continue

        if response.status_code == 200:
            return response.content
        if response.status_code == 404:
            raise DamFileNotAvailable(f"No DAM file published for {day.isoformat()} ({url})")

        last_error = RuntimeError(f"HTTP {response.status_code} for {url}")
        logger.warning(
            "Attempt %d/%d to fetch %s returned status %d",
            attempt,
            REQUEST_RETRIES,
            url,
            response.status_code,
        )
        time.sleep(REQUEST_BACKOFF_SECONDS * attempt)

    raise DamFileNotAvailable(
        f"Could not fetch DAM file for {day.isoformat()} after {REQUEST_RETRIES} attempts: {last_error}"
    )


def fetch_dam_hourly(day: date, session: requests.Session | None = None) -> pd.DataFrame:
    """Download the DAM workbook for ``day`` and return hourly-averaged MCP prices.

    Returns a DataFrame with columns ``hour`` (0-23), ``mcp`` (EUR/MWh) and
    ``date`` (the delivery day). Raises :class:`DamFileNotAvailable` if EnEx
    hasn't published the file yet, and :class:`DamFileMalformed` if the
    workbook doesn't have the expected columns.
    """
    owns_session = session is None
    session = session or requests.Session()
    try:
        content = _download(day, session)
    finally:
        if owns_session:
            session.close()

    try:
        raw = pd.read_excel(BytesIO(content), sheet_name=0, engine="openpyxl")
    except Exception as exc:  # corrupted/unexpected workbook content
        raise DamFileMalformed(f"Could not parse DAM workbook for {day.isoformat()}: {exc}") from exc

    missing_columns = REQUIRED_COLUMNS - set(raw.columns)
    if missing_columns:
        raise DamFileMalformed(
            f"DAM workbook for {day.isoformat()} is missing columns: {sorted(missing_columns)}"
        )

    clean = raw[["DELIVERY_MTU", "MCP"]].drop_duplicates(subset=["DELIVERY_MTU"])
    clean = clean.assign(hour=pd.to_datetime(clean["DELIVERY_MTU"]).dt.hour)

    hourly = clean.groupby("hour", as_index=False)["MCP"].mean()
    hourly = hourly.rename(columns={"MCP": "mcp"})
    hourly["date"] = day
    return hourly[["hour", "mcp", "date"]].sort_values("hour").reset_index(drop=True)
