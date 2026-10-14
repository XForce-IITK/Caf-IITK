"""Order tracking (UC-14; FR-40) with the ownership rule of FR-7."""

import uuid

from sqlalchemy.orm import Session

from app.models.identity import User
from app.modules.audit.service import record_security_event
from app.modules.ordering.repository import OrderRepository
from app.modules.ordering.schemas import OrderDetailOut


class OrderNotFoundError(Exception):
    """No such order, or it is another Student's: both answer 404 (FR-7)."""


class OrderTrackingService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = OrderRepository(session)

    def get_for_student(self, student: User, order_id: uuid.UUID) -> OrderDetailOut:
        """The Student's own order with its history.

        Asking for another Student's order is answered exactly like asking for one
        that does not exist, so its existence is not revealed, and is recorded as a
        security event once the read transaction has closed.
        """
        with self.session.begin():
            order = self.repo.find_order(order_id)
            if order is not None and order.student_id == student.id:
                return OrderDetailOut.from_history(
                    order,
                    self.repo.latest_snapshot(order_id),
                    self.repo.get_transitions(order_id),
                )
            belongs_to_someone_else = order is not None
        if belongs_to_someone_else:
            record_security_event(
                self.session,
                action="ORDER_ACCESS_DENIED",
                actor_id=str(student.id),
                actor_role=student.role.value,
                details={"order_id": str(order_id)},
            )
        raise OrderNotFoundError
