"""Preparation starts automatically (UC-18, FR-44, US-35).

At slot start - P-AUTO_PREP, every order of that slot still ACCEPTED moves to
PREPARING (T5), recorded with actor SYSTEM. It is the kitchen's own Start
transition (CAFIITK-159) with no user: each order row is locked and its status
re-checked first, and `OrderService._move` records the transition and the audit
entry and bumps the version, so a Student acting on what they saw before gets
409. Runs as a caf-worker job.
"""

import uuid
from datetime import datetime, timedelta
from functools import partial

from sqlalchemy.orm import Session

from app.models.enums import OrderStatus
from app.modules.ordering.retry import run_in_transaction
from app.modules.ordering.service import OrderService
from app.modules.payments.gateway import AuthResult

AUTO_PREP_REASON = "auto-prep"


class _NoPayments:
    """T5 moves no money; any payment call here would be a bug, so it fails loudly."""

    def authorise(self, reference: str, amount_paise: int) -> AuthResult:
        raise RuntimeError("auto-prep must not take payments")

    def void(self, reference: str) -> None:
        raise RuntimeError("auto-prep must not void payments")

    def refund(self, reference: str, auth_reference: str, amount_paise: int) -> None:
        raise RuntimeError("auto-prep must not refund payments")


class AutoPrepService(OrderService):
    def __init__(self, session: Session) -> None:
        super().__init__(session, _NoPayments())

    def start_due(self, now: datetime) -> int:
        """Move every due ACCEPTED order to PREPARING; returns how many moved."""
        with self.session.begin():
            lead = int(self.repo.get_settings("P-AUTO_PREP_MIN")["P-AUTO_PREP_MIN"])
            due = self.repo.accepted_orders_starting_by(now + timedelta(minutes=lead))
        # One short transaction per order, so one busy order does not hold the others.
        return sum(run_in_transaction(self.session, partial(self._start, oid)) for oid in due)

    def _start(self, order_id: uuid.UUID) -> bool:
        order = self.repo.lock_order(order_id)
        if order.status is not OrderStatus.ACCEPTED:
            return False  # the kitchen started it, or the Student cancelled, meanwhile
        self._move(order, OrderStatus.PREPARING, reason=AUTO_PREP_REASON)
        return True
