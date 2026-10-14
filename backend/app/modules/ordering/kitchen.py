"""Kitchen transitions (UC-17; FR-29, FR-43): Start, Mark Ready, Mark Picked Up and
Mark No-show, each a row of Table 4.6-A applied through the order state machine.

The order row is locked first, as everywhere (NFR-4), and the transition's portion
and seat effects come from the state machine: none for T5, T8 and T10, and none for
T11 either, so a no-show restores nothing and is not refunded.
"""

import uuid
from datetime import datetime, timedelta

from app.core.clock import IST
from app.models.enums import OrderStatus
from app.models.identity import User
from app.modules.kitchen.schemas import KitchenAction, KitchenOrderOut
from app.modules.ordering.retry import run_in_transaction
from app.modules.ordering.service import OrderService
from app.modules.ordering.tracking import OrderNotFoundError

_TARGET = {
    KitchenAction.START: OrderStatus.PREPARING,
    KitchenAction.READY: OrderStatus.READY,
    KitchenAction.PICKED_UP: OrderStatus.PICKED_UP,
    KitchenAction.NO_SHOW: OrderStatus.NO_SHOW,
}


class NoShowTooEarlyError(Exception):
    """T11's guard: only from slot end + P-NOSHOW_GRACE (Table 4.6-A): 409."""

    def __init__(self, allowed_from: datetime) -> None:
        super().__init__(f"no-show allowed from {allowed_from.isoformat()}")
        self.allowed_from = allowed_from


class KitchenTransitionService(OrderService):
    def advance(
        self, staff: User, order_id: uuid.UUID, action: KitchenAction, now: datetime
    ) -> KitchenOrderOut:
        """Raises OrderNotFoundError, IllegalTransitionError (409, nothing changes,
        FR-29) or NoShowTooEarlyError."""
        return run_in_transaction(self.session, lambda: self._advance(staff, order_id, action, now))

    def _advance(
        self, staff: User, order_id: uuid.UUID, action: KitchenAction, now: datetime
    ) -> KitchenOrderOut:
        if self.repo.find_order(order_id) is None:
            raise OrderNotFoundError
        order = self.repo.lock_order(order_id)
        if action is KitchenAction.NO_SHOW and order.status is OrderStatus.READY:
            slot = self.repo.get_slot(order.slot_id)
            assert slot is not None
            grace = int(self.repo.get_settings("P-NOSHOW_GRACE_MIN")["P-NOSHOW_GRACE_MIN"])
            # Shown as wall-clock IST, like every other service time (SRS Table 4.0-B).
            allowed_from = (slot.ends_at + timedelta(minutes=grace)).astimezone(IST)
            if now < allowed_from:
                raise NoShowTooEarlyError(allowed_from)
        self._move(order, _TARGET[action], actor=staff)
        return KitchenOrderOut(
            id=order.id, status=order.status, slot_id=order.slot_id, version=order.version
        )
