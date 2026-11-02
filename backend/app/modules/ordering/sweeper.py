"""Release expired holds (UC-15; FR-34, NFR-14, NFR-15, US-24).

Every P-SWEEP_INTERVAL, and once when caf-worker starts:

(a) an order still PENDING_PAYMENT more than P-HOLD_EXPIRY after it was created
    moves to PAYMENT_FAILED (reason "expired"), T3, which returns its portions
    and seat;
(b) a modification still HOLDING more than P-HOLD_EXPIRY after it was created
    gives back the extra portions and the new seat it took, and the order stays
    exactly as it was before the modification (FR-36).

Either way the authorisation may still land, so a void is queued in the payment
outbox; mockpay refuses a late approval for a reference voided first. A payment
result that arrives afterwards finds the order or modification no longer pending
and changes nothing (`OrderService._settle`, `ModifyService._settle_charge`).

The sweeper calls no gateway itself. Each order is handled in its own short
transaction under the order lock, so it serialises with a concurrent settle,
cancel or kitchen transition (NFR-5).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial

from sqlalchemy.orm import Session

from app.models.enums import (
    ModificationStatus,
    OrderStatus,
    PaymentCause,
    PaymentKind,
    PaymentStatus,
)
from app.models.ordering import Payment
from app.modules.ordering.auto_prep import _NoPayments
from app.modules.ordering.modification import ModifyService
from app.modules.ordering.retry import run_in_transaction
from app.modules.ordering.service import SYSTEM

EXPIRED_REASON = "expired"
_SYSTEM_ACTOR = {"actor_role": SYSTEM}


@dataclass(frozen=True)
class SweepResult:
    orders_expired: int = 0
    modifications_released: int = 0


class HoldSweeper(ModifyService):
    def __init__(self, session: Session, hold_expiry_s: int) -> None:
        super().__init__(session, _NoPayments())
        self.hold_expiry = timedelta(seconds=hold_expiry_s)

    def sweep(self, now: datetime) -> SweepResult:
        cutoff = now - self.hold_expiry
        with self.session.begin():
            orders = self.repo.stale_pending_orders(cutoff)
            modifications = self.repo.stale_holding_modifications(cutoff)
        expired = sum(
            run_in_transaction(self.session, partial(self._expire_order, oid)) for oid in orders
        )
        released = sum(
            run_in_transaction(self.session, partial(self._expire_modification, oid, mid))
            for oid, mid in modifications
        )
        return SweepResult(expired, released)

    def _expire_order(self, order_id: uuid.UUID) -> bool:
        order = self.repo.lock_order(order_id)
        if order.status is not OrderStatus.PENDING_PAYMENT:
            return False  # the payment result arrived meanwhile
        self._move(order, OrderStatus.PAYMENT_FAILED, reason=EXPIRED_REASON)
        self._void_pending_auth(order_id, None)
        return True

    def _expire_modification(self, order_id: uuid.UUID, modification_id: uuid.UUID) -> bool:
        # Canonical lock order: the order, then the modification, inventory and slot.
        order = self.repo.lock_order(order_id)
        modification = self.repo.get_modification(modification_id)
        if modification.status is not ModificationStatus.HOLDING:
            return False  # applied or released meanwhile
        # While HOLDING the order still has its old cart and slot, so what the hold
        # took is the difference to the new ones; a cancel or kitchen transition
        # in the meantime does not change the lines either.
        old = self._current_lines(order_id)
        new = {uuid.UUID(line["item_id"]): int(line["qty"]) for line in modification.new_lines}
        deltas = {item_id: new.get(item_id, 0) - old.get(item_id, 0) for item_id in old | new}
        slot = self.repo.get_slot(order.slot_id)
        assert slot is not None
        moved_to = modification.new_slot_id if modification.new_slot_id != order.slot_id else None
        self._release_taken(
            modification, order_id, slot.service_date, deltas, moved_to, _SYSTEM_ACTOR
        )
        self._void_pending_auth(order_id, modification_id)
        return True

    def _void_pending_auth(self, order_id: uuid.UUID, modification_id: uuid.UUID | None) -> None:
        """The authorisation never got a result: mark it failed and queue its void."""
        auth = self.repo.find_auth(order_id, modification_id)
        if auth is None:
            return  # a modification that lowered the price takes no payment
        if auth.status is not PaymentStatus.PENDING:
            return
        auth.status = PaymentStatus.FAILED
        if not self.repo.has_void(order_id, modification_id):
            self.repo.add(
                Payment(
                    id=uuid.uuid4(),
                    order_id=order_id,
                    modification_id=modification_id,
                    kind=PaymentKind.VOID,
                    cause=PaymentCause.EXPIRY,
                    amount_paise=auth.amount_paise,
                )
            )
