"""The cafeteria's clock. Service dates and slot times are IST wall-clock (SRS Table 4.0-B)."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def now() -> datetime:
    return datetime.now(IST)


def current_service_date() -> date:
    return now().date()
