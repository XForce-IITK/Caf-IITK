import uuid
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.capacity import ServiceDay, Slot
from app.models.ordering import Order
from app.models.platform import Setting


class SlotRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_setting(self, key: str) -> Any:
        return self.session.scalar(select(Setting.value).where(Setting.key == key))

    def list_for_date(self, service_date: date) -> list[Slot]:
        return list(
            self.session.scalars(
                select(Slot).where(Slot.service_date == service_date).order_by(Slot.starts_at)
            )
        )

    def lock_or_create_day(
        self,
        service_date: date,
        *,
        window_start: time,
        window_end: time,
        slot_len_min: int,
        default_capacity: int,
    ) -> tuple[ServiceDay, bool]:
        """Return the service day locked FOR UPDATE, inserting it if absent.

        Returns (day, created). Concurrent first-time configurations both proceed
        past the insert and then serialise on the row lock.
        """
        inserted = self.session.execute(
            insert(ServiceDay)
            .values(
                service_date=service_date,
                window_start=window_start,
                window_end=window_end,
                slot_len_min=slot_len_min,
                default_capacity=default_capacity,
            )
            .on_conflict_do_nothing()
            .returning(ServiceDay.service_date)
        ).first()
        day = self.session.scalars(
            select(ServiceDay)
            .where(ServiceDay.service_date == service_date)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one()
        return day, inserted is not None

    def lock_slots(self, service_date: date) -> list[Slot]:
        """The day's slots locked FOR UPDATE in ascending id, the system-wide slot lock order.

        Order placement locks its slot the same way before it books a seat, so once
        these locks are held no order can reach a slot of this day until we commit.
        """
        return list(
            self.session.scalars(
                select(Slot)
                .where(Slot.service_date == service_date)
                .order_by(Slot.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )

    def lock_slot(self, slot_id: uuid.UUID) -> Slot | None:
        return self.session.scalars(
            select(Slot)
            .where(Slot.id == slot_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one_or_none()

    def slot_ids_with_orders(self, slot_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        """Slots referenced by any order, in any state; their rows can never be deleted."""
        return set(
            self.session.scalars(
                select(Order.slot_id).where(Order.slot_id.in_(slot_ids)).distinct()
            )
        )

    def delete_slots(self, slot_ids: list[uuid.UUID]) -> None:
        self.session.execute(delete(Slot).where(Slot.id.in_(slot_ids)))

    def add_slots(
        self, service_date: date, bounds: list[tuple[datetime, datetime]], capacity: int
    ) -> list[Slot]:
        slots = [
            Slot(service_date=service_date, starts_at=start, ends_at=end, capacity=capacity)
            for start, end in bounds
        ]
        self.session.add_all(slots)
        self.session.flush()
        for slot in slots:
            self.session.refresh(slot)  # load server defaults (id, booked)
        return slots
