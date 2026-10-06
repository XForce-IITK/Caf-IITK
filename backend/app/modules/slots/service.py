"""Service window and pickup-slot configuration (FR-17, US-14)."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.identity import User
from app.modules.audit.service import write_audit
from app.modules.slots.domain import not_bookable_reason
from app.modules.slots.repository import SlotRepository
from app.modules.slots.schemas import (
    ServiceDayConfig,
    ServiceDayOut,
    SlotAvailabilityOut,
    SlotListOut,
    SlotOut,
)

# Service windows and slot times are IST wall-clock (SRS Table 4.0-B).
IST = ZoneInfo("Asia/Kolkata")


class SlotLengthError(Exception):
    """The slot length does not divide the service window evenly (US-14 AC2)."""

    def __init__(self, window_min: int, slot_len_min: int) -> None:
        super().__init__(
            f"slot length {slot_len_min} min does not divide the {window_min}-minute window"
        )


class DayHasOrdersError(Exception):
    """Slots of this day are referenced by orders, so they cannot be regenerated."""


def slot_bounds(
    service_date: date, window_start: time, window_end: time, slot_len_min: int
) -> list[tuple[datetime, datetime]]:
    """Consecutive [start, end) slots covering the window exactly, in IST."""
    start = datetime.combine(service_date, window_start, IST)
    end = datetime.combine(service_date, window_end, IST)
    window_min = int((end - start).total_seconds() // 60)
    if window_min % slot_len_min:
        raise SlotLengthError(window_min, slot_len_min)
    step = timedelta(minutes=slot_len_min)
    return [(start + i * step, start + (i + 1) * step) for i in range(window_min // slot_len_min)]


class SlotService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = SlotRepository(session)

    def configure_day(
        self, admin: User, service_date: date, config: ServiceDayConfig
    ) -> ServiceDayOut:
        """FR-17: set the window, slot length and capacity, and (re)generate the slots.

        Re-configuring replaces the slots only while no order references any of them;
        otherwise nothing changes (changing a live slot's capacity is US-15). The day
        row is updated in place so daily_inventory rows that reference it survive.
        """
        try:
            with self.session.begin():
                slot_len = config.slot_len_min or int(self.repo.get_setting("P-SLOT_LEN_MIN"))
                bounds = slot_bounds(service_date, config.window_start, config.window_end, slot_len)
                day, created = self.repo.lock_or_create_day(
                    service_date,
                    window_start=config.window_start,
                    window_end=config.window_end,
                    slot_len_min=slot_len,
                    default_capacity=config.default_capacity,
                )
                before = None
                if not created:
                    if self.repo.day_has_orders(service_date):
                        raise DayHasOrdersError
                    before = _day_summary(
                        day.window_start, day.window_end, day.slot_len_min, day.default_capacity
                    )
                    day.window_start = config.window_start
                    day.window_end = config.window_end
                    day.slot_len_min = slot_len
                    day.default_capacity = config.default_capacity
                slots = self.repo.replace_slots(service_date, bounds, config.default_capacity)
                write_audit(
                    self.session,
                    action="SERVICE_DAY_CONFIGURED",
                    entity_type="service_day",
                    entity_id=service_date.isoformat(),
                    actor_id=str(admin.id),
                    actor_role=admin.role.value,
                    before=before,
                    after=_day_summary(
                        config.window_start, config.window_end, slot_len, config.default_capacity
                    )
                    | {"slots": len(slots)},
                )
        except IntegrityError as exc:
            # An order was placed on one of the old slots while we were replacing them;
            # its foreign key stopped the delete.
            raise DayHasOrdersError from exc

        return ServiceDayOut(
            service_date=service_date,
            window_start=config.window_start,
            window_end=config.window_end,
            slot_len_min=slot_len,
            default_capacity=config.default_capacity,
            slots=[SlotOut.model_validate(s) for s in slots],
        )

    def browse_slots(self, service_date: date, now: datetime) -> SlotListOut:
        """FR-19 / US-16: the date's slots with remaining seats and whether each is bookable."""
        with self.session.begin():
            book_close_min = int(self.repo.get_setting("P-BOOK_CLOSE_MIN"))
            slots = self.repo.list_for_date(service_date)
        out = []
        for slot in slots:
            reason = not_bookable_reason(
                capacity=slot.capacity,
                booked=slot.booked,
                starts_at=slot.starts_at,
                now=now,
                book_close_min=book_close_min,
            )
            out.append(
                SlotAvailabilityOut(
                    id=slot.id,
                    starts_at=slot.starts_at,
                    ends_at=slot.ends_at,
                    remaining_seats=slot.capacity - slot.booked,
                    bookable=reason is None,
                    not_bookable_reason=reason,
                )
            )
        return SlotListOut(service_date=service_date, slots=out)


def _day_summary(
    window_start: time, window_end: time, slot_len_min: int, capacity: int
) -> dict[str, str | int]:
    return {
        "window_start": window_start.isoformat(timespec="minutes"),
        "window_end": window_end.isoformat(timespec="minutes"),
        "slot_len_min": slot_len_min,
        "default_capacity": capacity,
    }
