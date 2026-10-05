from datetime import date, datetime, time
from typing import Any

from sqlalchemy import delete, exists, select
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

    def day_has_orders(self, service_date: date) -> bool:
        """Any order, in any state, that references a slot of this day."""
        return bool(
            self.session.scalar(
                select(
                    exists()
                    .where(Order.slot_id == Slot.id)
                    .where(Slot.service_date == service_date)
                )
            )
        )

    def replace_slots(
        self, service_date: date, bounds: list[tuple[datetime, datetime]], capacity: int
    ) -> list[Slot]:
        self.session.execute(delete(Slot).where(Slot.service_date == service_date))
        slots = [
            Slot(service_date=service_date, starts_at=start, ends_at=end, capacity=capacity)
            for start, end in bounds
        ]
        self.session.add_all(slots)
        self.session.flush()
        for slot in slots:
            self.session.refresh(slot)  # load server defaults (id, booked)
        return slots
