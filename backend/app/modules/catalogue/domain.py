"""The orderability rule (FR-12), shared by the menu and by order placement."""

from datetime import datetime
from enum import StrEnum

from app.models.enums import ItemStatus


class NotOrderableReason(StrEnum):
    REMOVED = "REMOVED"
    UNAVAILABLE = "UNAVAILABLE"
    SOLD_OUT = "SOLD_OUT"


def is_flagged(unavailable: bool, unavailable_until: datetime | None, now: datetime) -> bool:
    """A flag with an end time (item-disable, FR-53) stops counting once that time has passed."""
    return unavailable and (unavailable_until is None or now < unavailable_until)


def not_orderable_reason(
    *,
    status: ItemStatus,
    unavailable: bool,
    unavailable_until: datetime | None,
    available: int,
    now: datetime,
) -> NotOrderableReason | None:
    """None if the item is orderable; otherwise why not.

    A flagged item reports UNAVAILABLE even when it also has no portions left:
    replenishing it would still not make it orderable.
    """
    if status is not ItemStatus.ACTIVE:
        return NotOrderableReason.REMOVED
    if is_flagged(unavailable, unavailable_until, now):
        return NotOrderableReason.UNAVAILABLE
    if available < 1:
        return NotOrderableReason.SOLD_OUT
    return None
