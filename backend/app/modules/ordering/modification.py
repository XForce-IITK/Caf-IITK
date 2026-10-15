"""Order modification by the Student (UC-12; FR-35, FR-36, FR-39): T4 of Table 4.6-A.

Same shape as placement (ADR-03), holding the old and the new resources together
until the price difference is settled, so the order never holds neither (FR-36):

1. One transaction checks ownership, state, cut-off and version under the
   canonical locks, takes only the extra portions and the new seat, re-prices,
   records the modification as HOLDING and bumps the order version, which turns
   away a concurrent cancel or modify (NFR-5).
2. If the price did not rise, the same transaction applies the change, and any
   refund of the difference is sent after commit.
3. If it rose, the difference is authorised with no transaction open (NFR-6); a
   second transaction then applies the change, or releases what step 1 took and
   leaves the order exactly as it was.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.models.capacity import Slot
from app.models.enums import (
    ModificationStatus,
    OrderStatus,
    PaymentCause,
    PaymentKind,
    PaymentStatus,
)
from app.models.identity import User
from app.models.ordering import Order, OrderModification, Payment, PriceSnapshot
from app.modules.audit.service import record_security_event, write_audit
from app.modules.ordering.retry import run_in_transaction
from app.modules.ordering.schemas import (
    ModificationQuoteOut,
    ModifiedOrderOut,
    ModifyOrderRequest,
    RefundOut,
)
from app.modules.ordering.service import (
    OrderConflictError,
    OrderService,
    PriceChangedError,
    UnavailableError,
    _orderable,
    _PendingRefund,
)
from app.modules.ordering.tracking import OrderNotFoundError
from app.modules.payments.gateway import AuthOutcome, AuthResult
from app.modules.pricing.schemas import QuoteOut, QuoteRequest
from app.modules.pricing.service import QuantityLimitError, QuoteService, SlotNotFoundError
from app.modules.slots.domain import not_bookable_reason

APPLIED = "APPLIED"


class NothingToChangeError(Exception):
    """The new cart and slot are the order's current ones: 422."""


class OtherServiceDateError(Exception):
    """Portions are stocked per service date, so the new slot must be on the order's: 422."""


class ModificationPaymentError(Exception):
    """The difference was not charged; the order is exactly as before (FR-36): 402."""

    def __init__(self, outcome: str) -> None:
        super().__init__(f"payment for the difference: {outcome.lower()}")
        self.outcome = outcome


@dataclass(frozen=True)
class _Change:
    """What step 1 took, so step 3 can apply or release exactly that."""

    order_id: uuid.UUID
    modification_id: uuid.UUID
    service_date: date
    old_slot_id: uuid.UUID
    new_slot_id: uuid.UUID
    deltas: dict[uuid.UUID, int]
    new_lines: dict[uuid.UUID, int]
    quote: QuoteOut
    # The version step 1 left; anything else means the order changed meanwhile.
    version: int

    @property
    def moves_slot(self) -> bool:
        return self.new_slot_id != self.old_slot_id


@dataclass(frozen=True)
class _Charge:
    change: _Change
    payment_id: uuid.UUID
    amount_paise: int


@dataclass(frozen=True)
class _Finished:
    order_id: uuid.UUID
    modification_id: uuid.UUID
    outcome: str
    refund: _PendingRefund | None = None


class ModifyService(OrderService):
    def quote(
        self, student: User, order_id: uuid.UUID, request: QuoteRequest
    ) -> ModificationQuoteOut:
        """UC-12 step 3, read-only: the new price, keeping this order's own subsidy."""
        actor_id, actor_role = str(student.id), student.role.value
        try:
            with self.session.begin():
                order = self._own_order(student, order_id)
                quote = QuoteService(self.session).price(student, request, repricing=order.id)
                return ModificationQuoteOut(
                    quote=quote,
                    paid_paise=order.paid_paise,
                    difference_paise=quote.payable_paise - order.paid_paise,
                )
        except OrderNotFoundError:
            self._deny(actor_id, actor_role, order_id, "quote_modification")
            raise

    def modify(
        self,
        student: User,
        order_id: uuid.UUID,
        request: ModifyOrderRequest,
        idempotency_key: str,
        now: datetime,
    ) -> ModifiedOrderOut:
        # Read before the transaction: a rollback expires `student` (see cancel).
        actor_id, actor_role = str(student.id), student.role.value
        try:
            held = run_in_transaction(
                self.session,
                lambda: self._hold(student, order_id, request, idempotency_key, now),
            )
        except OrderNotFoundError:
            self._deny(actor_id, actor_role, order_id, "modify")
            raise
        if isinstance(held, _Charge):
            # The payments row id is the reference, so repeating the call is safe.
            result = self.gateway.authorise(str(held.payment_id), held.amount_paise)
            held = run_in_transaction(
                self.session, lambda: self._settle_charge(held, result, student, idempotency_key)
            )
        if held.refund is not None:
            self._deliver_refund(held.refund)
        if held.outcome != APPLIED:
            raise ModificationPaymentError(held.outcome)
        return self._modified_view(held.order_id, held.modification_id)

    def _deny(self, actor_id: str, actor_role: str, order_id: uuid.UUID, operation: str) -> None:
        record_security_event(
            self.session,
            action="ORDER_ACCESS_DENIED",
            actor_id=actor_id,
            actor_role=actor_role,
            details={"order_id": str(order_id), "operation": operation},
        )

    def _own_order(self, student: User, order_id: uuid.UUID) -> Order:
        found = self.repo.find_order(order_id)
        if found is None or found.student_id != student.id:
            raise OrderNotFoundError
        return found

    def _hold(
        self,
        student: User,
        order_id: uuid.UUID,
        request: ModifyOrderRequest,
        idempotency_key: str,
        now: datetime,
    ) -> _Charge | _Finished:
        """Step 1, and step 2 when no charge is needed. Raising rolls everything back."""
        replay = self.idempotency.claim(
            student.id,
            idempotency_key,
            {"order_id": str(order_id), **request.model_dump(mode="json")},
        )
        if replay is not None:
            return _Finished(
                uuid.UUID(replay.response["order_id"]),
                uuid.UUID(replay.response["modification_id"]),
                replay.response["outcome"],
            )

        self._own_order(student, order_id)
        order = self.repo.lock_order(order_id)
        settings = self.repo.get_settings("P-CUTOFF_MIN", "P-BOOK_CLOSE_MIN", "P-MAX_QTY")
        if order.status is not OrderStatus.ACCEPTED:
            raise OrderConflictError(f"order is {order.status.value}", order)
        old_slot = self.repo.get_slot(order.slot_id)
        assert old_slot is not None
        if now >= old_slot.starts_at - timedelta(minutes=int(settings["P-CUTOFF_MIN"])):
            raise OrderConflictError("the modification cut-off has passed", order)
        if order.version != request.version:
            raise OrderConflictError("the order has changed", order)

        max_qty = int(settings["P-MAX_QTY"])
        if any(line.qty > max_qty for line in request.lines):
            raise QuantityLimitError(max_qty)
        new_slot = self.repo.get_slot(request.slot_id)
        if new_slot is None:
            raise SlotNotFoundError
        if new_slot.service_date != old_slot.service_date:
            raise OtherServiceDateError

        old_lines = {line.item_id: line.qty for line in self.repo.get_lines(order.id)}
        new_lines = {line.item_id: line.qty for line in request.lines}
        if new_lines == old_lines and new_slot.id == old_slot.id:
            raise NothingToChangeError
        deltas = {
            item_id: new_lines.get(item_id, 0) - old_lines.get(item_id, 0)
            for item_id in old_lines.keys() | new_lines.keys()
        }
        deltas = {item_id: delta for item_id, delta in deltas.items() if delta}

        # Serialises the Student's subsidy with their placements, as placement does.
        self.repo.lock_student(student.id)
        # Unknown and removed items are refused here (422), before any counter is locked.
        quote = QuoteService(self.session).price(
            student, QuoteRequest(slot_id=new_slot.id, lines=request.lines), repricing=order.id
        )

        # Canonical lock order (NFR-4): the order (held), inventory by item id, slots by id.
        items = self.repo.get_items(list(deltas))
        stock = self.repo.lock_inventory(list(deltas), old_slot.service_date)
        slots = self._lock_slots(old_slot, new_slot)
        unavailable = [
            item_id
            for item_id, delta in deltas.items()
            if delta > 0 and not _orderable(items[item_id], stock.get(item_id), delta, now)
        ]
        slot_unbookable = new_slot.id != old_slot.id and (
            not_bookable_reason(
                capacity=slots[new_slot.id].capacity,
                booked=slots[new_slot.id].booked,
                starts_at=new_slot.starts_at,
                now=now,
                book_close_min=int(settings["P-BOOK_CLOSE_MIN"]),
            )
            is not None
        )
        if unavailable or slot_unbookable:
            raise UnavailableError(unavailable, new_slot.id if slot_unbookable else None)
        if quote.payable_paise != request.quoted_payable_paise:
            raise PriceChangedError(quote)

        # Take only what the order does not hold yet; the old holds stay (FR-36).
        actor = {"actor_id": str(student.id), "actor_role": student.role.value}
        for item_id, delta in deltas.items():
            if delta > 0:
                self._change_allocated(
                    stock[item_id], delta, "PORTIONS_ALLOCATED", order.id, **actor
                )
        if new_slot.id != old_slot.id:
            self._change_seat(slots[new_slot.id], 1, order.id, actor)

        difference = quote.payable_paise - order.paid_paise
        modification = OrderModification(
            id=uuid.uuid4(),
            order_id=order.id,
            status=ModificationStatus.HOLDING,
            new_slot_id=new_slot.id,
            new_lines=[{"item_id": str(i), "qty": q} for i, q in new_lines.items()],
            diff_paise=difference,
        )
        self.repo.add(modification)
        order.version += 1
        change = _Change(
            order.id,
            modification.id,
            old_slot.service_date,
            old_slot.id,
            new_slot.id,
            deltas,
            new_lines,
            quote,
            order.version,
        )

        if difference > 0:
            payment = Payment(
                id=uuid.uuid4(),
                order_id=order.id,
                modification_id=modification.id,
                kind=PaymentKind.AUTH,
                cause=PaymentCause.MODIFY,
                amount_paise=difference,
            )
            self.repo.add(payment)
            return _Charge(change, payment.id, difference)

        refund = self._apply(order, modification, change, student)
        self._complete(student, idempotency_key, change, APPLIED)
        return _Finished(order.id, modification.id, APPLIED, refund)

    def _settle_charge(
        self, held: _Charge, result: AuthResult, student: User, idempotency_key: str
    ) -> _Finished:
        """Step 3: apply the change if the difference was charged; otherwise release it."""
        change = held.change
        order = self.repo.lock_order(change.order_id)
        modification = self.repo.get_modification(change.modification_id)
        payment = self.repo.get_payment(held.payment_id)
        approved = result.outcome is AuthOutcome.APPROVED
        payment.status = PaymentStatus.SUCCEEDED if approved else PaymentStatus.FAILED
        payment.provider_ref = result.provider_ref
        payment.attempts += 1

        still_ours = (
            modification.status is ModificationStatus.HOLDING
            and order.status is OrderStatus.ACCEPTED
            and order.version == change.version
        )
        if approved and still_ours:
            self._apply(order, modification, change, student)
            outcome = APPLIED
        else:
            if modification.status is ModificationStatus.HOLDING:
                self._release(modification, change, student)
            # A cancel or the hold sweeper got there first: the charge is not kept.
            outcome = result.outcome.value if not approved else "SUPERSEDED"
            # A timed-out authorisation may still have landed, so it is voided too.
            if result.outcome is not AuthOutcome.DECLINED:
                self.repo.add(
                    Payment(
                        id=uuid.uuid4(),
                        order_id=change.order_id,
                        modification_id=change.modification_id,
                        kind=PaymentKind.VOID,
                        cause=PaymentCause.MODIFY,
                        amount_paise=held.amount_paise,
                    )
                )
        self._complete(student, idempotency_key, change, outcome)
        return _Finished(change.order_id, change.modification_id, outcome)

    def _apply(
        self, order: Order, modification: OrderModification, change: _Change, student: User
    ) -> _PendingRefund | None:
        """Release what the order no longer needs and make the new cart and slot its own."""
        actor = {"actor_id": str(student.id), "actor_role": student.role.value}
        released = [item_id for item_id, delta in change.deltas.items() if delta < 0]
        if released:
            stock = self.repo.lock_inventory(released, change.service_date)
            for item_id in released:
                self._change_allocated(
                    stock[item_id],
                    change.deltas[item_id],
                    "PORTIONS_RELEASED",
                    order.id,
                    **actor,
                )
        if change.moves_slot:
            # Both slots, by ascending id (NFR-4), even though only the old one's counter
            # changes: setting orders.slot_id below takes a key-share lock on the new slot
            # through the foreign key, which would otherwise come after the old slot's
            # lock whatever their ids, and deadlock against a move the other way.
            slots = {
                slot_id: self.repo.lock_slot(slot_id)
                for slot_id in sorted([change.old_slot_id, change.new_slot_id])
            }
            self._change_seat(slots[change.old_slot_id], -1, order.id, actor)

        before = {
            "slot_id": str(order.slot_id),
            "paid_paise": order.paid_paise,
            "lines": {str(i): q for i, q in self._current_lines(order.id).items()},
        }
        self.repo.replace_lines(order.id, change.new_lines)
        snapshot_version = self.repo.latest_snapshot(order.id).version + 1
        self.repo.add(
            PriceSnapshot(
                order_id=order.id,
                version=snapshot_version,
                breakdown=change.quote.model_dump(mode="json"),
                payable_paise=change.quote.payable_paise,
            )
        )
        order.slot_id = change.new_slot_id
        order.paid_paise = change.quote.payable_paise
        order.subsidy_applied = change.quote.subsidy_paise > 0
        order.version += 1
        modification.status = ModificationStatus.APPLIED
        self._record_transition(order, OrderStatus.ACCEPTED, actor=student, reason="modified")
        write_audit(
            self.session,
            action="ORDER_MODIFIED",
            entity_type="order",
            entity_id=str(order.id),
            before=before,
            after={
                "slot_id": str(order.slot_id),
                "paid_paise": order.paid_paise,
                "lines": {str(i): q for i, q in change.new_lines.items()},
                "snapshot_version": snapshot_version,
                "modification_id": str(modification.id),
            },
            **actor,
        )
        if modification.diff_paise >= 0:
            return None
        refund = Payment(
            id=uuid.uuid4(),
            order_id=order.id,
            modification_id=modification.id,
            kind=PaymentKind.REFUND,
            cause=PaymentCause.MODIFY,
            amount_paise=-modification.diff_paise,
            status=PaymentStatus.PENDING,
        )
        return self._record_refund(refund, student)

    def _release(self, modification: OrderModification, change: _Change, student: User) -> None:
        """Give back what step 1 took; the order keeps its old cart and slot (FR-36)."""
        actor = {"actor_id": str(student.id), "actor_role": student.role.value}
        taken = [item_id for item_id, delta in change.deltas.items() if delta > 0]
        if taken:
            stock = self.repo.lock_inventory(taken, change.service_date)
            for item_id in taken:
                self._change_allocated(
                    stock[item_id],
                    -change.deltas[item_id],
                    "PORTIONS_RELEASED",
                    change.order_id,
                    **actor,
                )
        if change.moves_slot:
            self._change_seat(self.repo.lock_slot(change.new_slot_id), -1, change.order_id, actor)
        modification.status = ModificationStatus.RELEASED

    def _lock_slots(self, old_slot: Slot, new_slot: Slot) -> dict[uuid.UUID, Slot]:
        """Both slots of a move, by ascending id (NFR-4); none when the slot stays."""
        if old_slot.id == new_slot.id:
            return {}
        return {
            slot_id: self.repo.lock_slot(slot_id) for slot_id in sorted([old_slot.id, new_slot.id])
        }

    def _change_seat(
        self, slot: Slot, delta: int, order_id: uuid.UUID, actor: dict[str, str]
    ) -> None:
        before = slot.booked
        slot.booked += delta
        write_audit(
            self.session,
            action="SEAT_ALLOCATED" if delta > 0 else "SEAT_RELEASED",
            entity_type="slot",
            entity_id=str(slot.id),
            before={"booked": before},
            after={"booked": slot.booked, "order_id": str(order_id)},
            **actor,
        )

    def _current_lines(self, order_id: uuid.UUID) -> dict[uuid.UUID, int]:
        return {line.item_id: line.qty for line in self.repo.get_lines(order_id)}

    def _complete(self, student: User, idempotency_key: str, change: _Change, outcome: str) -> None:
        self.idempotency.complete(
            student.id,
            idempotency_key,
            {
                "order_id": str(change.order_id),
                "modification_id": str(change.modification_id),
                "outcome": outcome,
            },
        )

    def _modified_view(self, order_id: uuid.UUID, modification_id: uuid.UUID) -> ModifiedOrderOut:
        modification = self.session.get_one(OrderModification, modification_id)
        refund = self.repo.find_modify_refund(modification_id)
        return ModifiedOrderOut(
            **self._view(order_id).model_dump(),
            difference_paise=modification.diff_paise,
            refund=RefundOut(amount_paise=refund.amount_paise, status=refund.status)
            if refund
            else None,
        )
