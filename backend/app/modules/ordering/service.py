"""Order placement (UC-11; FR-30, FR-33): reserve → authorise → confirm (ADR-03).

1. One transaction locks the rows, re-validates, re-prices, allocates the portions
   and the seat and commits the order in PENDING_PAYMENT.
2. The payment gateway is called with no transaction open (NFR-6).
3. A second transaction moves the order to ACCEPTED, or to PAYMENT_FAILED and
   returns its holds.

Cancellation by the Student (UC-13; FR-37, FR-39) commits T6 or T7 together with
exactly one refund record, then sends the refund with no transaction open.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from sqlalchemy.orm import Session

from app.core.clock import IST
from app.models.capacity import DailyInventory
from app.models.catalogue import MenuItem
from app.models.enums import OrderStatus, PaymentCause, PaymentKind, PaymentStatus
from app.models.identity import User
from app.models.ordering import Order, OrderLine, OrderTransition, Payment, PriceSnapshot
from app.modules.audit.service import record_security_event, write_audit
from app.modules.catalogue.domain import not_orderable_reason
from app.modules.ordering.idempotency import IdempotencyService
from app.modules.ordering.refunds import RefundPart, refund_parts
from app.modules.ordering.repository import OrderRepository
from app.modules.ordering.retry import run_in_transaction
from app.modules.ordering.schemas import (
    CancelledOrderOut,
    CancelOrderRequest,
    OrderOut,
    PlaceOrderRequest,
    RefundOut,
)
from app.modules.ordering.state_machine import transition
from app.modules.ordering.tracking import OrderNotFoundError
from app.modules.payments.gateway import (
    AuthOutcome,
    AuthResult,
    PaymentGateway,
    PaymentGatewayError,
)
from app.modules.pricing.schemas import QuoteOut
from app.modules.pricing.service import (
    QuantityLimitError,
    QuoteService,
    SlotNotFoundError,
    UnknownItemsError,
)
from app.modules.slots.domain import not_bookable_reason

logger = logging.getLogger(__name__)

SYSTEM = "SYSTEM"


class MenuNotOpenError(Exception):
    """Ordering for this service date opens at P-MENU_OPEN (FR-30)."""

    def __init__(self, opens_at: datetime) -> None:
        super().__init__(f"ordering opens at {opens_at.isoformat()}")
        self.opens_at = opens_at


class UnavailableError(Exception):
    """Items that are not orderable (FR-12) and/or a slot that is not bookable (FR-19)."""

    def __init__(self, item_ids: list[uuid.UUID], slot_id: uuid.UUID | None) -> None:
        super().__init__("items or slot unavailable")
        self.item_ids = item_ids
        self.slot_id = slot_id


class PriceChangedError(Exception):
    """The amount at confirmation differs from the quoted one (FR-26)."""

    def __init__(self, quote: QuoteOut) -> None:
        super().__init__("price changed since the quote")
        self.quote = quote


class OrderConflictError(Exception):
    """The order cannot be cancelled now (FR-37, NFR-5): 409 with the reason.

    Carries the order's current state, and the refund a cancel would now give if it
    is still allowed, so the client can show both and ask again (UC-13 3c).
    """

    def __init__(self, reason: str, order: Order, refund_paise: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = order.status
        self.version = order.version
        self.refund_paise = refund_paise


@dataclass(frozen=True)
class _Reservation:
    order_id: uuid.UUID
    payment_id: uuid.UUID
    amount_paise: int


@dataclass(frozen=True)
class _PendingRefund:
    order_id: uuid.UUID
    refund_id: uuid.UUID
    parts: list[RefundPart]


# T6 and T7 are the Student's cancels (FR-37); READY and terminal states are refused.
_STUDENT_CANCELLABLE = frozenset({OrderStatus.ACCEPTED, OrderStatus.PREPARING})


def cancel_refund_paise(status: OrderStatus, paid_paise: int, late_refund_pct: int) -> int:
    """Table 4.6-A: 100 % from ACCEPTED (T6), P-LATE_REFUND_PCT from PREPARING (T7).

    Money is integer paise, so the percentage is rounded half-up to the paisa.
    """
    if status is OrderStatus.ACCEPTED:
        return paid_paise
    return (paid_paise * late_refund_pct + 50) // 100


def _orderable(item: MenuItem, stock: DailyInventory | None, qty: int, now: datetime) -> bool:
    """FR-12 as the menu shows it, and enough portions for this line."""
    available = stock.total - stock.allocated if stock else 0
    reason = not_orderable_reason(
        status=item.status,
        unavailable=item.unavailable,
        unavailable_until=item.unavailable_until,
        available=available,
        now=now,
    )
    return reason is None and available >= qty


class OrderService:
    def __init__(self, session: Session, gateway: PaymentGateway) -> None:
        self.session = session
        self.gateway = gateway
        self.repo = OrderRepository(session)
        self.idempotency = IdempotencyService(session)

    def place(
        self, student: User, request: PlaceOrderRequest, idempotency_key: str, now: datetime
    ) -> OrderOut:
        reserved = run_in_transaction(
            self.session, lambda: self._reserve(student, request, idempotency_key, now)
        )
        if isinstance(reserved, OrderOut):
            return reserved
        # The payments row id is the reference, so repeating the call is safe.
        result = self.gateway.authorise(str(reserved.payment_id), reserved.amount_paise)
        return run_in_transaction(self.session, lambda: self._settle(reserved, result))

    def _reserve(
        self, student: User, request: PlaceOrderRequest, idempotency_key: str, now: datetime
    ) -> OrderOut | _Reservation:
        """T1. Raising rolls everything back, the idempotency claim included."""
        replay = self.idempotency.claim(
            student.id, idempotency_key, request.model_dump(mode="json")
        )
        if replay is not None:
            return self._view(uuid.UUID(replay.response["order_id"]))

        settings = self.repo.get_settings("P-MENU_OPEN", "P-BOOK_CLOSE_MIN", "P-MAX_QTY")
        max_qty = int(settings["P-MAX_QTY"])
        if any(line.qty > max_qty for line in request.lines):
            raise QuantityLimitError(max_qty)

        slot = self.repo.get_slot(request.slot_id)
        if slot is None:
            raise SlotNotFoundError
        opens_at = datetime.combine(
            slot.service_date, time.fromisoformat(settings["P-MENU_OPEN"]), IST
        )
        if now < opens_at:
            raise MenuNotOpenError(opens_at)

        item_ids = [line.item_id for line in request.lines]
        items = self.repo.get_items(item_ids)
        unknown = [item_id for item_id in item_ids if item_id not in items]
        if unknown:
            raise UnknownItemsError(unknown)

        self.repo.lock_student(student.id)
        stock = self.repo.lock_inventory(item_ids, slot.service_date)
        slot = self.repo.lock_slot(slot.id)

        # Checked under the locks, so the counters cannot move before we commit.
        unavailable = [
            line.item_id
            for line in request.lines
            if not _orderable(items[line.item_id], stock.get(line.item_id), line.qty, now)
        ]
        slot_unbookable = (
            not_bookable_reason(
                capacity=slot.capacity,
                booked=slot.booked,
                starts_at=slot.starts_at,
                now=now,
                book_close_min=int(settings["P-BOOK_CLOSE_MIN"]),
            )
            is not None
        )
        if unavailable or slot_unbookable:
            raise UnavailableError(unavailable, slot.id if slot_unbookable else None)

        quote = QuoteService(self.session).price(student, request)
        if quote.payable_paise != request.quoted_payable_paise:
            raise PriceChangedError(quote)

        order = Order(
            id=uuid.uuid4(),
            student_id=student.id,
            slot_id=slot.id,
            status=OrderStatus.PENDING_PAYMENT,
            subsidy_applied=quote.subsidy_paise > 0,
        )
        payment = Payment(
            id=uuid.uuid4(),
            order_id=order.id,
            kind=PaymentKind.AUTH,
            cause=PaymentCause.CREATE,
            amount_paise=quote.payable_paise,
        )
        self.repo.add(order)
        self.repo.add(
            *(
                OrderLine(order_id=order.id, item_id=line.item_id, qty=line.qty)
                for line in request.lines
            ),
            PriceSnapshot(
                order_id=order.id,
                version=1,
                breakdown=quote.model_dump(mode="json"),
                payable_paise=quote.payable_paise,
            ),
            payment,
        )
        self._record_transition(order, None, actor=student)

        actor = {"actor_id": str(student.id), "actor_role": student.role.value}
        for line in request.lines:
            row = stock[line.item_id]
            self._change_allocated(row, line.qty, "PORTIONS_ALLOCATED", order.id, **actor)
        before = slot.booked
        slot.booked += 1
        write_audit(
            self.session,
            action="SEAT_ALLOCATED",
            entity_type="slot",
            entity_id=str(slot.id),
            before={"booked": before},
            after={"booked": slot.booked, "order_id": str(order.id)},
            **actor,
        )

        self.idempotency.complete(student.id, idempotency_key, {"order_id": str(order.id)})
        return _Reservation(order.id, payment.id, quote.payable_paise)

    def _settle(self, reserved: _Reservation, result: AuthResult) -> OrderOut:
        """T2 or T3, guarded by the order still being PENDING_PAYMENT (ADR-03)."""
        order = self.repo.lock_order(reserved.order_id)
        payment = self.repo.get_payment(reserved.payment_id)
        approved = result.outcome is AuthOutcome.APPROVED
        payment.status = PaymentStatus.SUCCEEDED if approved else PaymentStatus.FAILED
        payment.provider_ref = result.provider_ref
        payment.attempts += 1
        # A timed-out authorisation may still have landed, so it is voided too (SADD 6.2).
        may_have_charged = result.outcome is not AuthOutcome.DECLINED

        if order.status is not OrderStatus.PENDING_PAYMENT:
            # The hold expired while we waited; the late result changes nothing (FR-34).
            if may_have_charged:
                self._queue_void(reserved)
        elif approved:
            order.paid_paise = reserved.amount_paise
            self._move(order, OrderStatus.ACCEPTED)
        else:
            self._move(order, OrderStatus.PAYMENT_FAILED, reason=result.outcome.value.lower())
            if may_have_charged:
                self._queue_void(reserved)
        return self._view(order.id)

    def cancel(
        self,
        student: User,
        order_id: uuid.UUID,
        request: CancelOrderRequest,
        idempotency_key: str,
        now: datetime,
    ) -> CancelledOrderOut:
        """UC-13: T6 or T7 in one transaction, then the mock refund with none open (NFR-6)."""
        # Read before the transaction: a rollback expires `student`, and reloading it
        # afterwards would open a transaction the security event cannot begin inside.
        actor_id, actor_role = str(student.id), student.role.value
        try:
            cancelled = run_in_transaction(
                self.session,
                lambda: self._cancel(student, order_id, request, idempotency_key, now),
            )
        except OrderNotFoundError:
            record_security_event(
                self.session,
                action="ORDER_ACCESS_DENIED",
                actor_id=actor_id,
                actor_role=actor_role,
                details={"order_id": str(order_id), "operation": "cancel"},
            )
            raise
        if isinstance(cancelled, _PendingRefund):
            self._deliver_refund(cancelled)
            order_id = cancelled.order_id
        return self._cancelled_view(order_id)

    def _cancel(
        self,
        student: User,
        order_id: uuid.UUID,
        request: CancelOrderRequest,
        idempotency_key: str,
        now: datetime,
    ) -> _PendingRefund | None:
        """Raising rolls everything back, the idempotency claim included.

        Returns None for a replay of a cancel that already happened (FR-32).
        """
        replay = self.idempotency.claim(
            student.id,
            idempotency_key,
            {"order_id": str(order_id), "version": request.version},
        )
        if replay is not None:
            return None

        found = self.repo.find_order(order_id)
        if found is None or found.student_id != student.id:
            raise OrderNotFoundError
        # Canonical lock order: the order first, then inventory and slot in _move (NFR-4).
        order = self.repo.lock_order(order_id)

        settings = self.repo.get_settings("P-CUTOFF_MIN", "P-LATE_REFUND_PCT")
        if order.status not in _STUDENT_CANCELLABLE:
            raise OrderConflictError(f"order is {order.status.value}", order)
        refund_paise = cancel_refund_paise(
            order.status, order.paid_paise, int(settings["P-LATE_REFUND_PCT"])
        )
        slot = self.repo.get_slot(order.slot_id)
        assert slot is not None
        cutoff = slot.starts_at - timedelta(minutes=int(settings["P-CUTOFF_MIN"]))
        if now >= cutoff:
            raise OrderConflictError("the cancellation cut-off has passed", order)
        if order.version != request.version:
            # The kitchen started it, or another request changed it, since the Student
            # looked: show the new state and refund and let them confirm again.
            raise OrderConflictError("the order has changed", order, refund_paise)

        self._move(order, OrderStatus.CANCELLED, actor=student, reason="cancelled by student")
        refund = Payment(
            id=uuid.uuid4(),
            order_id=order.id,
            kind=PaymentKind.REFUND,
            cause=PaymentCause.CANCEL,
            amount_paise=refund_paise,
            # Nothing to send for a zero refund; the record still exists (FR-39).
            status=PaymentStatus.PENDING if refund_paise else PaymentStatus.SUCCEEDED,
        )
        pending = self._record_refund(refund, student)
        self.idempotency.complete(student.id, idempotency_key, {"order_id": str(order.id)})
        return pending

    def _record_refund(self, refund: Payment, actor: User) -> _PendingRefund | None:
        """Add the refund record and work out the parts to send; None if nothing to send."""
        self.repo.add(refund)
        write_audit(
            self.session,
            action="REFUND_RECORDED",
            entity_type="payment",
            entity_id=str(refund.id),
            actor_id=str(actor.id),
            actor_role=actor.role.value,
            after={
                "order_id": str(refund.order_id),
                "amount_paise": refund.amount_paise,
                "cause": refund.cause.value,
            },
        )
        if not refund.amount_paise:
            return None
        parts = refund_parts(
            self.repo.get_charges(refund.order_id),
            self.repo.get_refunds(refund.order_id),
            refund.id,
        )
        return _PendingRefund(refund.order_id, refund.id, parts)

    def _deliver_refund(self, pending: _PendingRefund) -> None:
        """Send the refund once; on failure it stays PENDING for the outbox retrier (FR-39).

        Each part's reference derives from the refund row id, so a retry can never
        refund twice.
        """
        try:
            for part in pending.parts:
                self.gateway.refund(part.reference, str(part.auth_id), part.amount_paise)
            delivered = True
        except PaymentGatewayError as exc:
            logger.warning("refund %s not acknowledged, left for retry: %s", pending.refund_id, exc)
            delivered = False

        def record() -> None:
            refund = self.repo.get_payment(pending.refund_id)
            refund.attempts += 1
            if delivered and refund.status is PaymentStatus.PENDING:
                refund.status = PaymentStatus.SUCCEEDED

        run_in_transaction(self.session, record)

    def _move(
        self,
        order: Order,
        to_status: OrderStatus,
        *,
        actor: User | None = None,
        reason: str | None = None,
    ) -> None:
        """Apply a transition of Table 4.6-A with its portion and seat effects.

        `actor` is the user who asked for it; None means the system did.
        """
        effects = transition(order.status, to_status)
        from_status = order.status
        audit_actor = (
            {"actor_id": str(actor.id), "actor_role": actor.role.value}
            if actor
            else {"actor_role": SYSTEM}
        )
        if effects.releases_portions:
            slot = self.repo.get_slot(order.slot_id)
            assert slot is not None
            lines = {line.item_id: line.qty for line in self.repo.get_lines(order.id)}
            stock = self.repo.lock_inventory(list(lines), slot.service_date)
            for item_id, row in stock.items():
                self._change_allocated(
                    row, -lines[item_id], "PORTIONS_RELEASED", order.id, **audit_actor
                )
        if effects.releases_seat:
            slot = self.repo.lock_slot(order.slot_id)
            before = slot.booked
            slot.booked -= 1
            write_audit(
                self.session,
                action="SEAT_RELEASED",
                entity_type="slot",
                entity_id=str(slot.id),
                before={"booked": before},
                after={"booked": slot.booked, "order_id": str(order.id)},
                **audit_actor,
            )
        order.status = to_status
        order.version += 1
        self._record_transition(order, from_status, actor=actor, reason=reason)

    def _change_allocated(
        self,
        row: DailyInventory,
        delta: int,
        action: str,
        order_id: uuid.UUID,
        *,
        actor_id: str | None = None,
        actor_role: str,
    ) -> None:
        before = row.allocated
        row.allocated += delta
        write_audit(
            self.session,
            action=action,
            entity_type="daily_inventory",
            entity_id=f"{row.item_id}:{row.service_date.isoformat()}",
            actor_id=actor_id,
            actor_role=actor_role,
            before={"allocated": before},
            after={"allocated": row.allocated, "order_id": str(order_id)},
        )

    def _record_transition(
        self,
        order: Order,
        from_status: OrderStatus | None,
        *,
        actor: User | None,
        reason: str | None = None,
    ) -> None:
        self.repo.add(
            OrderTransition(
                order_id=order.id,
                from_status=from_status,
                to_status=order.status,
                actor_id=actor.id if actor else None,
                actor_role=actor.role if actor else None,
                reason=reason,
            )
        )
        write_audit(
            self.session,
            action="ORDER_TRANSITION",
            entity_type="order",
            entity_id=str(order.id),
            actor_id=str(actor.id) if actor else None,
            actor_role=actor.role.value if actor else SYSTEM,
            before={"status": from_status.value if from_status else None},
            after={"status": order.status.value, "reason": reason},
        )

    def _queue_void(self, reserved: _Reservation) -> None:
        """Outbox row; the worker delivers it to the gateway until acknowledged."""
        self.repo.add(
            Payment(
                id=uuid.uuid4(),
                order_id=reserved.order_id,
                kind=PaymentKind.VOID,
                cause=PaymentCause.CREATE,
                amount_paise=reserved.amount_paise,
            )
        )

    def _view(self, order_id: uuid.UUID) -> OrderOut:
        return OrderOut.from_rows(
            self.repo.get_order(order_id), self.repo.latest_snapshot(order_id)
        )

    def _cancelled_view(self, order_id: uuid.UUID) -> CancelledOrderOut:
        refund = self.repo.find_cancel_refund(order_id)
        assert refund is not None
        return CancelledOrderOut(
            **self._view(order_id).model_dump(),
            refund=RefundOut(amount_paise=refund.amount_paise, status=refund.status),
        )
