import uuid
from datetime import date
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.capacity import DailyInventory, Slot
from app.models.catalogue import MenuItem
from app.models.enums import PaymentCause, PaymentKind, PaymentStatus
from app.models.identity import User
from app.models.ordering import (
    Order,
    OrderLine,
    OrderModification,
    OrderTransition,
    Payment,
    PriceSnapshot,
)
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

    def find_order(self, order_id: uuid.UUID) -> Order | None:
        return self.session.scalars(
            select(Order).where(Order.id == order_id).execution_options(populate_existing=True)
        ).one_or_none()

    def get_transitions(self, order_id: uuid.UUID) -> list[OrderTransition]:
        """Oldest first; the id breaks ties between changes in one transaction."""
        return list(
            self.session.scalars(
                select(OrderTransition)
                .where(OrderTransition.order_id == order_id)
                .order_by(OrderTransition.at, OrderTransition.id)
            )
        )

    def get_lines(self, order_id: uuid.UUID) -> list[OrderLine]:
        return list(self.session.scalars(select(OrderLine).where(OrderLine.order_id == order_id)))

    def get_payment(self, payment_id: uuid.UUID) -> Payment:
        return self.session.scalars(
            select(Payment)
            .where(Payment.id == payment_id)
            .execution_options(populate_existing=True)
        ).one()

    def get_charges(self, order_id: uuid.UUID) -> list[tuple[uuid.UUID, int]]:
        """Approved authorisations (placement and price rises), oldest first."""
        rows = self.session.execute(
            select(Payment.id, Payment.amount_paise)
            .where(
                Payment.order_id == order_id,
                Payment.kind == PaymentKind.AUTH,
                Payment.status == PaymentStatus.SUCCEEDED,
            )
            .order_by(Payment.created_at, Payment.id)
        )
        return [(payment_id, amount) for payment_id, amount in rows]

    def get_refunds(self, order_id: uuid.UUID) -> list[tuple[uuid.UUID, int]]:
        """Every refund record of the order, in the order they were recorded."""
        rows = self.session.execute(
            select(Payment.id, Payment.amount_paise)
            .where(Payment.order_id == order_id, Payment.kind == PaymentKind.REFUND)
            .order_by(Payment.created_at, Payment.id)
        )
        return [(payment_id, amount) for payment_id, amount in rows]

    def get_modification(self, modification_id: uuid.UUID) -> OrderModification:
        return self.session.scalars(
            select(OrderModification)
            .where(OrderModification.id == modification_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one()

    def find_modify_refund(self, modification_id: uuid.UUID) -> Payment | None:
        """At most one exists: uq_payments_modify_refund (FR-39)."""
        return self.session.scalars(
            select(Payment).where(
                Payment.modification_id == modification_id,
                Payment.kind == PaymentKind.REFUND,
                Payment.cause == PaymentCause.MODIFY,
            )
        ).one_or_none()

    def replace_lines(self, order_id: uuid.UUID, lines: dict[uuid.UUID, int]) -> None:
        self.session.execute(delete(OrderLine).where(OrderLine.order_id == order_id))
        self.add(*(OrderLine(order_id=order_id, item_id=i, qty=q) for i, q in lines.items()))

    def find_cancel_refund(self, order_id: uuid.UUID) -> Payment | None:
        """At most one exists: uq_payments_cancel_refund (FR-39)."""
        return self.session.scalars(
            select(Payment)
            .where(
                Payment.order_id == order_id,
                Payment.kind == PaymentKind.REFUND,
                Payment.cause == PaymentCause.CANCEL,
            )
            .execution_options(populate_existing=True)
        ).one_or_none()

    def latest_snapshot(self, order_id: uuid.UUID) -> PriceSnapshot:
        return self.session.scalars(
            select(PriceSnapshot)
            .where(PriceSnapshot.order_id == order_id)
            .order_by(PriceSnapshot.version.desc())
            .limit(1)
        ).one()
