import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.capacity import DailyInventory, Slot
from app.models.catalogue import MenuItem
from app.models.identity import User
from app.models.ordering import Order, OrderLine, Payment, PriceSnapshot
from app.models.platform import Setting


class OrderRepository:
    """Row locks here follow the canonical order (NFR-4, ADR-02):
    order → daily_inventory by ascending item id → slot.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, *rows: Any) -> None:
        self.session.add_all(rows)
        self.session.flush()

    def get_settings(self, *keys: str) -> dict[str, Any]:
        rows = self.session.execute(select(Setting.key, Setting.value).where(Setting.key.in_(keys)))
        return {key: value for key, value in rows}

    def get_slot(self, slot_id: uuid.UUID) -> Slot | None:
        return self.session.get(Slot, slot_id)

    def get_items(self, item_ids: list[uuid.UUID]) -> dict[uuid.UUID, MenuItem]:
        """Items of any status, read fresh so a just-set flag or removal is seen."""
        rows = self.session.scalars(
            select(MenuItem)
            .where(MenuItem.id.in_(item_ids))
            .execution_options(populate_existing=True)
        )
        return {item.id: item for item in rows}

    def lock_student(self, student_id: uuid.UUID) -> None:
        """Serialise one Student's placements, so two cannot both take the day's subsidy.

        FOR NO KEY UPDATE, because the idempotency-key insert already holds a
        FOR KEY SHARE lock on this row through its foreign key.
        """
        self.session.execute(
            select(User.id).where(User.id == student_id).with_for_update(key_share=True)
        )

    def lock_inventory(
        self, item_ids: list[uuid.UUID], service_date: date
    ) -> dict[uuid.UUID, DailyInventory]:
        rows = self.session.scalars(
            select(DailyInventory)
            .where(
                DailyInventory.item_id.in_(item_ids), DailyInventory.service_date == service_date
            )
            .order_by(DailyInventory.item_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return {row.item_id: row for row in rows}

    def lock_slot(self, slot_id: uuid.UUID) -> Slot:
        return self.session.scalars(
            select(Slot)
            .where(Slot.id == slot_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one()

    def lock_order(self, order_id: uuid.UUID) -> Order:
        return self.session.scalars(
            select(Order)
            .where(Order.id == order_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one()

    def get_order(self, order_id: uuid.UUID) -> Order:
        return self.session.scalars(
            select(Order).where(Order.id == order_id).execution_options(populate_existing=True)
        ).one()

    def get_lines(self, order_id: uuid.UUID) -> list[OrderLine]:
        return list(self.session.scalars(select(OrderLine).where(OrderLine.order_id == order_id)))

    def get_payment(self, payment_id: uuid.UUID) -> Payment:
        return self.session.scalars(
            select(Payment)
            .where(Payment.id == payment_id)
            .execution_options(populate_existing=True)
        ).one()

    def latest_snapshot(self, order_id: uuid.UUID) -> PriceSnapshot:
        return self.session.scalars(
            select(PriceSnapshot)
            .where(PriceSnapshot.order_id == order_id)
            .order_by(PriceSnapshot.version.desc())
            .limit(1)
        ).one()
