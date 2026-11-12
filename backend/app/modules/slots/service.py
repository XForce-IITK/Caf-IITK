"""Service window and pickup-slot configuration (FR-17, FR-18; US-14, US-15)."""

import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.capacity import Slot
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


class SlotNotFoundError(Exception):
    pass


class SlotHasOrdersError(Exception):
    """A reconfiguration would remove a slot that orders reference (FR-18, US-15 AC2)."""

    def __init__(self, starts_at: datetime | None = None) -> None:
        which = f"the {starts_at.astimezone(IST):%H:%M} slot" if starts_at else "a slot"
        super().__init__(f"{which} has orders and would be removed")


class CapacityBelowBookedError(Exception):
    """A capacity below a slot's booked seats (FR-18, US-15 AC1)."""

    def __init__(self, slot: Slot, capacity: int) -> None:
        self.slot_id = slot.id
        super().__init__(
            f"the {slot.starts_at.astimezone(IST):%H:%M} slot has {slot.booked} seats booked; "
            f"capacity {capacity} is too low"
        )


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
        self, admin: User, service_date: date, config: ServiceDayConfig, now: datetime
    ) -> ServiceDayOut:
        """FR-17: set the window, slot length and capacity, and (re)generate the slots.

        A slot that orders reference is kept, with its id and bookings, and given the
        new default capacity; the configuration is refused if it would remove such a
        slot or take its capacity below its booked seats (FR-18). A slot with orders
        that has already ended is history: it is kept as it is even outside the new
        window, so the rest of the day can still be reconfigured. Every other slot is
        regenerated, except where it would overlap a kept one. The day row is updated
        in place so daily_inventory rows survive.
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
                kept: list[Slot] = []
                if not created:
                    before = _day_summary(
                        day.window_start, day.window_end, day.slot_len_min, day.default_capacity
                    )
                    kept = self._keep_slots_with_orders(service_date, bounds, config, now)
                    day.window_start = config.window_start
                    day.window_end = config.window_end
                    day.slot_len_min = slot_len
                    day.default_capacity = config.default_capacity
                new = [
                    (start, end)
                    for start, end in bounds
                    if not any(start < s.ends_at and s.starts_at < end for s in kept)
                ]
                slots = kept + self.repo.add_slots(service_date, new, config.default_capacity)
                slots.sort(key=lambda s: s.starts_at)
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
                    | {"slots": len(slots), "kept_with_orders": len(kept)},
                )
        except IntegrityError as exc:
            # Defence in depth: the slot locks should make this unreachable, but an
            # order's foreign key would stop us deleting a slot it references.
            raise SlotHasOrdersError from exc

        return ServiceDayOut(
            service_date=service_date,
            window_start=config.window_start,
            window_end=config.window_end,
            slot_len_min=slot_len,
            default_capacity=config.default_capacity,
            slots=[SlotOut.model_validate(s) for s in slots],
        )

    def _keep_slots_with_orders(
        self,
        service_date: date,
        bounds: list[tuple[datetime, datetime]],
        config: ServiceDayConfig,
        now: datetime,
    ) -> list[Slot]:
        """Delete the day's slots that no order references; return the others.

        A kept slot in the new bounds takes the new capacity; one that has ended and is
        outside them is left as it is. Raises before changing anything if a referenced
        slot that has not ended is not in the new bounds, or has more seats booked than
        the new capacity.
        """
        current = self.repo.lock_slots(service_date)
        with_orders = self.repo.slot_ids_with_orders([s.id for s in current])
        kept = sorted((s for s in current if s.id in with_orders), key=lambda s: s.starts_at)
        wanted = set(bounds)
        in_window = [s for s in kept if (s.starts_at, s.ends_at) in wanted]
        for slot in kept:
            if slot not in in_window and slot.ends_at > now:
                raise SlotHasOrdersError(slot.starts_at)
        for slot in in_window:
            if slot.booked > config.default_capacity:
                raise CapacityBelowBookedError(slot, config.default_capacity)
        for slot in in_window:
            slot.capacity = config.default_capacity
        self.repo.delete_slots([s.id for s in current if s.id not in with_orders])
        return kept

    def change_capacity(self, admin: User, slot_id: uuid.UUID, capacity: int) -> Slot:
        """FR-18 / US-15: change one slot's capacity; never below its booked seats.

        The slot is locked as order placement locks it, so a seat booked concurrently is
        counted before the check. Setting the current capacity again writes nothing.
        """
        with self.session.begin():
            slot = self.repo.lock_slot(slot_id)
            if slot is None:
                raise SlotNotFoundError
            if capacity < slot.booked:
                raise CapacityBelowBookedError(slot, capacity)
            if capacity != slot.capacity:
                write_audit(
                    self.session,
                    action="SLOT_CAPACITY_CHANGED",
                    entity_type="slot",
                    entity_id=str(slot.id),
                    actor_id=str(admin.id),
                    actor_role=admin.role.value,
                    before={"capacity": slot.capacity, "booked": slot.booked},
                    after={"capacity": capacity, "booked": slot.booked},
                )
                slot.capacity = capacity
            return slot

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
