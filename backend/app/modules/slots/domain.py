"""The bookable rule (FR-19), shared by the slot list and by order placement."""

from datetime import datetime, timedelta
from enum import StrEnum


class NotBookableReason(StrEnum):
    CLOSED = "CLOSED"
    FULL = "FULL"


def not_bookable_reason(
    *, capacity: int, booked: int, starts_at: datetime, now: datetime, book_close_min: int
) -> NotBookableReason | None:
    """None if the slot is bookable; otherwise why not.

    Booking closes P-BOOK_CLOSE before the slot starts. A closed slot reports
    CLOSED even when it is also full: a freed seat would not reopen it.
    """
    if now >= starts_at - timedelta(minutes=book_close_min):
        return NotBookableReason.CLOSED
    if capacity - booked < 1:
        return NotBookableReason.FULL
    return None
