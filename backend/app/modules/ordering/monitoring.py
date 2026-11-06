"""The Administrator's view of a service day (UC-19; FR-45, FR-46)."""

import uuid
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models.enums import OrderStatus
from app.modules.ordering.repository import MonitoringRepository
from app.modules.ordering.schemas import (
    AdminOrderOut,
    ItemUtilisationOut,
    OrderOut,
    SlotUtilisationOut,
    UtilisationOut,
)

# How many orders one page of the Administrator's list returns at most; a day has
# up to about 1,000 (NFR-12).
MAX_ADMIN_LISTED_ORDERS = 1000


class MonitoringService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = MonitoringRepository(session)

    def list_orders(
        self,
        service_date: date,
        *,
        statuses: list[OrderStatus] | None = None,
        slot_id: uuid.UUID | None = None,
        student: str | None = None,
        limit: int = MAX_ADMIN_LISTED_ORDERS,
    ) -> list[AdminOrderOut]:
        """FR-45: the date's orders, filtered by state, slot and Student, by slot time."""
        with self.session.begin():
            rows = self.repo.list_day_orders(
                service_date, statuses=statuses, slot_id=slot_id, student=student, limit=limit
            )
            return [
                AdminOrderOut(
                    **OrderOut.from_rows(order, snapshot).model_dump(),
                    student_id=user.id,
                    student_name=user.name,
                    student_email=user.email,
                    slot_starts_at=slot.starts_at,
                )
                for order, snapshot, user, slot in rows
            ]

    def utilisation(self, service_date: date, now: datetime) -> UtilisationOut:
        """FR-46: booked/capacity per slot, allocated/total/available per item, and the
        count of orders in each state, all read in one transaction."""
        with self.session.begin():
            slots = self.repo.day_slots(service_date)
            items = self.repo.day_items(service_date)
            counts = self.repo.day_order_counts(service_date)
            return UtilisationOut(
                service_date=service_date,
                as_of=now,
                slots=[
                    SlotUtilisationOut(
                        slot_id=s.id,
                        starts_at=s.starts_at,
                        ends_at=s.ends_at,
                        booked=s.booked,
                        capacity=s.capacity,
                    )
                    for s in slots
                ],
                items=[
                    ItemUtilisationOut(
                        item_id=item.id,
                        name=item.name,
                        allocated=allocated,
                        total=total,
                        available=total - allocated,
                    )
                    for item, total, allocated in items
                ],
                order_counts={status: counts.get(status, 0) for status in OrderStatus},
            )
