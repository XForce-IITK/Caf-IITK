"""The payment outbox (FR-34, FR-39; SADD 6.2): deliver voids and refunds until acknowledged.

A void (of a timed-out, superseded or expired authorisation) and a refund that
mockpay did not acknowledge are left as PENDING `payments` rows. This caf-worker
job sends each one again until the gateway acknowledges it, then marks it
SUCCEEDED. References derive from the row ids, so a repeat is harmless: mockpay
answers a repeated void or refund with the original result.

Like every gateway call, the call is made with no transaction open (NFR-6): one
transaction reads what to send, the call follows, a second records the outcome.
"""

import logging
import uuid
from functools import partial

from sqlalchemy.orm import Session

from app.models.enums import PaymentKind, PaymentStatus
from app.modules.ordering.refunds import InsufficientChargesError, refund_parts
from app.modules.ordering.retry import run_in_transaction
from app.modules.ordering.service import OrderService, _PendingRefund
from app.modules.payments.gateway import PaymentGateway, PaymentGatewayError

logger = logging.getLogger(__name__)

# Rows handled per run; the rest wait for the next interval.
BATCH = 100


class OutboxDeliverer(OrderService):
    def __init__(self, session: Session, gateway: PaymentGateway) -> None:
        super().__init__(session, gateway)

    def deliver(self) -> int:
        """Send every pending void and refund once; returns how many were acknowledged."""
        with self.session.begin():
            pending = self.repo.pending_outbox(BATCH)
        return sum(self._deliver_one(payment_id) for payment_id in pending)

    def _deliver_one(self, payment_id: uuid.UUID) -> bool:
        try:
            work = run_in_transaction(self.session, partial(self._what_to_send, payment_id))
        except InsufficientChargesError:
            # The order's accounting is wrong; retrying cannot fix it.
            logger.error("refund %s exceeds what was charged; left PENDING", payment_id)
            return False
        if work is None:
            return False
        if isinstance(work, _PendingRefund):
            self._deliver_refund(work)
        else:
            self._deliver_void(payment_id, work)
        with self.session.begin():
            return self.repo.get_payment(payment_id).status is PaymentStatus.SUCCEEDED

    def _what_to_send(self, payment_id: uuid.UUID) -> _PendingRefund | str | None:
        """A refund's parts, a void's authorisation reference, or None if already done."""
        payment = self.repo.get_payment(payment_id)
        if payment.status is not PaymentStatus.PENDING:
            return None  # the request that recorded it delivered it meanwhile
        if payment.kind is PaymentKind.REFUND:
            parts = refund_parts(
                self.repo.get_charges(payment.order_id),
                self.repo.get_refunds(payment.order_id),
                payment.id,
            )
            return _PendingRefund(payment.order_id, payment.id, parts)
        auth = self.repo.find_auth(payment.order_id, payment.modification_id)
        if auth is None:
            logger.error("void %s has no authorisation to void; left PENDING", payment_id)
            return None
        # The authorisation's reference is its payments row id (OrderService.place).
        return str(auth.id)

    def _deliver_void(self, void_id: uuid.UUID, auth_reference: str) -> None:
        try:
            self.gateway.void(auth_reference)
            delivered = True
        except PaymentGatewayError as exc:
            logger.warning("void %s not acknowledged, left for retry: %s", void_id, exc)
            delivered = False

        def record() -> None:
            void = self.repo.get_payment(void_id)
            void.attempts += 1
            if delivered and void.status is PaymentStatus.PENDING:
                void.status = PaymentStatus.SUCCEEDED

        run_in_transaction(self.session, record)
