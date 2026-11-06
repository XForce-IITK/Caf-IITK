import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, aliased

from app.models.capacity import DailyInventory, Slot
from app.models.catalogue import MenuItem
from app.models.enums import (
    ItemStatus,
    ModificationStatus,
    OrderStatus,
    PaymentCause,
    PaymentKind,
    PaymentStatus,
)
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

# Not yet finished: these count towards P-MAX_ACTIVE (FR-31).
ACTIVE_STATUSES = frozenset(
    {OrderStatus.PENDING_PAYMENT, OrderStatus.ACCEPTED, OrderStatus.PREPARING, OrderStatus.READY}
)


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

    def count_active_orders(self, student_id: uuid.UUID, service_date: date) -> int:
        """The Student's non-terminal orders for slots on `service_date` (FR-31)."""
        return (
            self.session.scalar(
                select(func.count())
                .select_from(Order)
                .join(Slot, Slot.id == Order.slot_id)
                .where(
                    Order.student_id == student_id,
                    Slot.service_date == service_date,
                    Order.status.in_(ACTIVE_STATUSES),
                )
            )
            or 0
        )

    def lock_inventory(
        self, item_ids: list[uuid.UUID], service_date: date
    ) -> dict[uuid.UUID, DailyInventory]:
        """FOR NO KEY UPDATE, like lock_slot: the counters are not keys."""
        rows = self.session.scalars(
            select(DailyInventory)
            .where(
                DailyInventory.item_id.in_(item_ids), DailyInventory.service_date == service_date
            )
            .order_by(DailyInventory.item_id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
        return {row.item_id: row for row in rows}

    def lock_slot(self, slot_id: uuid.UUID) -> Slot:
        """FOR NO KEY UPDATE: a placement inserts its order, whose foreign key takes
        FOR KEY SHARE on the slot, before it locks the slot (CAFIITK-189). FOR UPDATE
        would wait on every other placement's KEY SHARE, while they wait on this one's
        inventory lock: a deadlock. Changing `booked` needs no stronger lock.
        """
        return self.session.scalars(
            select(Slot)
            .where(Slot.id == slot_id)
            .with_for_update(key_share=True)
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

    def accepted_orders_starting_by(self, cutoff: datetime) -> list[uuid.UUID]:
        """ACCEPTED orders whose slot starts at or before `cutoff`, in lock order (NFR-4)."""
        return list(
            self.session.scalars(
                select(Order.id)
                .join(Slot, Slot.id == Order.slot_id)
                .where(Order.status == OrderStatus.ACCEPTED, Slot.starts_at <= cutoff)
                .order_by(Order.id)
            )
        )

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
        """Approved authorisations (placement and price rises) that were kept, oldest first.

        A late approval that was voided (FR-34) is SUCCEEDED but is not a charge:
        mockpay refuses any refund against it.
        """
        void = aliased(Payment)
        voided = (
            select(void.id)
            .where(
                void.order_id == Payment.order_id,
                void.kind == PaymentKind.VOID,
                void.modification_id.is_not_distinct_from(Payment.modification_id),
            )
            .exists()
        )
        rows = self.session.execute(
            select(Payment.id, Payment.amount_paise)
            .where(
                Payment.order_id == order_id,
                Payment.kind == PaymentKind.AUTH,
                Payment.status == PaymentStatus.SUCCEEDED,
                ~voided,
            )
            .order_by(Payment.created_at, Payment.id)
        )
        return [(payment_id, amount) for payment_id, amount in rows]

    def find_auth(self, order_id: uuid.UUID, modification_id: uuid.UUID | None) -> Payment | None:
        """The authorisation of a placement (no modification) or of one modification."""
        return self.session.scalars(
            select(Payment)
            .where(
                Payment.order_id == order_id,
                Payment.kind == PaymentKind.AUTH,
                Payment.modification_id.is_not_distinct_from(modification_id),
            )
            .execution_options(populate_existing=True)
        ).one_or_none()

    def has_void(self, order_id: uuid.UUID, modification_id: uuid.UUID | None) -> bool:
        return (
            self.session.scalar(
                select(Payment.id)
                .where(
                    Payment.order_id == order_id,
                    Payment.kind == PaymentKind.VOID,
                    Payment.modification_id.is_not_distinct_from(modification_id),
                )
                .limit(1)
            )
            is not None
        )

    def stale_pending_orders(self, created_before: datetime) -> list[uuid.UUID]:
        """PENDING_PAYMENT orders older than the hold expiry, in lock order (FR-34a)."""
        return list(
            self.session.scalars(
                select(Order.id)
                .where(
                    Order.status == OrderStatus.PENDING_PAYMENT,
                    Order.created_at < created_before,
                )
                .order_by(Order.id)
            )
        )

    def stale_holding_modifications(
        self, created_before: datetime
    ) -> list[tuple[uuid.UUID, uuid.UUID]]:
        """(order id, modification id) of HOLDING modifications older than the hold expiry."""
        rows = self.session.execute(
            select(OrderModification.order_id, OrderModification.id)
            .where(
                OrderModification.status == ModificationStatus.HOLDING,
                OrderModification.created_at < created_before,
            )
            .order_by(OrderModification.order_id, OrderModification.id)
        )
        return [(order_id, modification_id) for order_id, modification_id in rows]

    def pending_outbox(self, limit: int) -> list[uuid.UUID]:
        """Voids and refunds not yet acknowledged by the gateway, oldest first."""
        return list(
            self.session.scalars(
                select(Payment.id)
                .where(
                    Payment.kind.in_([PaymentKind.VOID, PaymentKind.REFUND]),
                    Payment.status == PaymentStatus.PENDING,
                )
                .order_by(Payment.created_at, Payment.id)
                .limit(limit)
            )
        )

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

    def get_snapshots(self, order_id: uuid.UUID) -> list[PriceSnapshot]:
        """Every price snapshot version of the order, v1 first (FR-27)."""
        return list(
            self.session.scalars(
                select(PriceSnapshot)
                .where(PriceSnapshot.order_id == order_id)
                .order_by(PriceSnapshot.version)
            )
        )

    def get_refund_payments(self, order_id: uuid.UUID) -> list[Payment]:
        """Every refund recorded for the order as full rows, oldest first (FR-28)."""
        return list(
            self.session.scalars(
                select(Payment)
                .where(Payment.order_id == order_id, Payment.kind == PaymentKind.REFUND)
                .order_by(Payment.created_at, Payment.id)
            )
        )

    def list_student_orders(
        self, student_id: uuid.UUID, limit: int
    ) -> list[tuple[Order, PriceSnapshot]]:
        """The Student's orders, newest first, each with its latest snapshot."""
        latest = (
            select(func.max(PriceSnapshot.version))
            .where(PriceSnapshot.order_id == Order.id)
            .correlate(Order)
            .scalar_subquery()
        )
        rows = self.session.execute(
            select(Order, PriceSnapshot)
            .join(
                PriceSnapshot,
                (PriceSnapshot.order_id == Order.id) & (PriceSnapshot.version == latest),
            )
            .where(Order.student_id == student_id)
            .order_by(Order.created_at.desc(), Order.id)
            .limit(limit)
        )
        return [(order, snapshot) for order, snapshot in rows.tuples()]

    def latest_snapshot(self, order_id: uuid.UUID) -> PriceSnapshot:
        return self.session.scalars(
            select(PriceSnapshot)
            .where(PriceSnapshot.order_id == order_id)
            .order_by(PriceSnapshot.version.desc())
            .limit(1)
        ).one()


class MonitoringRepository:
    """Read-only queries behind the Administrator's day view (FR-45, FR-46)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_day_orders(
        self,
        service_date: date,
        *,
        statuses: list[OrderStatus] | None,
        slot_id: uuid.UUID | None,
        student: str | None,
        limit: int,
    ) -> list[tuple[Order, PriceSnapshot, User, Slot]]:
        """Orders in the date's slots, by slot then placement time, each with its latest
        snapshot, its Student and its slot. `student` matches part of a name or email."""
        latest = (
            select(func.max(PriceSnapshot.version))
            .where(PriceSnapshot.order_id == Order.id)
            .correlate(Order)
            .scalar_subquery()
        )
        query = (
            select(Order, PriceSnapshot, User, Slot)
            .join(Slot, Slot.id == Order.slot_id)
            .join(User, User.id == Order.student_id)
            .join(
                PriceSnapshot,
                (PriceSnapshot.order_id == Order.id) & (PriceSnapshot.version == latest),
            )
            .where(Slot.service_date == service_date)
        )
        if statuses:
            query = query.where(Order.status.in_(statuses))
        if slot_id is not None:
            query = query.where(Order.slot_id == slot_id)
        if student:
            pattern = (
                "%" + student.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            )
            query = query.where(
                User.name.ilike(pattern, escape="\\") | User.email.ilike(pattern, escape="\\")
            )
        rows = self.session.execute(
            query.order_by(Slot.starts_at, Order.created_at, Order.id).limit(limit)
        )
        return [(order, snapshot, user, slot) for order, snapshot, user, slot in rows.tuples()]

    def day_slots(self, service_date: date) -> list[Slot]:
        return list(
            self.session.scalars(
                select(Slot).where(Slot.service_date == service_date).order_by(Slot.starts_at)
            )
        )

    def day_items(self, service_date: date) -> list[tuple[MenuItem, int, int]]:
        """(item, total, allocated) for every item with portions set for the date, and
        every ACTIVE item without any (0, 0), by name."""
        rows = self.session.execute(
            select(
                MenuItem,
                func.coalesce(DailyInventory.total, 0),
                func.coalesce(DailyInventory.allocated, 0),
            )
            .outerjoin(
                DailyInventory,
                (DailyInventory.item_id == MenuItem.id)
                & (DailyInventory.service_date == service_date),
            )
            .where((MenuItem.status == ItemStatus.ACTIVE) | DailyInventory.item_id.is_not(None))
            .order_by(func.lower(MenuItem.name), MenuItem.id)
        )
        return [(item, total, allocated) for item, total, allocated in rows.tuples()]

    def day_order_counts(self, service_date: date) -> dict[OrderStatus, int]:
        rows = self.session.execute(
            select(Order.status, func.count())
            .join(Slot, Slot.id == Order.slot_id)
            .where(Slot.service_date == service_date)
            .group_by(Order.status)
        )
        return {status: count for status, count in rows.tuples()}
