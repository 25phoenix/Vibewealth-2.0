"""Shared financial precision and calendar rules."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

MAX_SAFE_PAISE = 2**53 - 1
FINANCIAL_TIMEZONE = ZoneInfo("Asia/Kolkata")


def financial_today() -> date:
    """Return the current date in the product's financial timezone."""

    return datetime.now(FINANCIAL_TIMEZONE).date()
