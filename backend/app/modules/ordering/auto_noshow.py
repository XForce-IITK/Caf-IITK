"""Uncollected orders are closed at the end of the service day (CAFIITK-210, T11).

Kitchen Staff mark a READY order No-show by hand once its slot has ended plus
P-NOSHOW_GRACE (FR-43). If they never do, the order would stay READY for ever:
the Student keeps seeing it as ready and pickup figures are wrong. So once the
service day's last slot has ended plus P-NOSHOW_GRACE, every order still READY
moves to NO_SHOW, recorded with actor SYSTEM.

Waiting for the end of the day, not the order's own slot, leaves staff free to
hand over a late pickup throughout service; T11's guard (slot end + grace) always
holds by then. The effects are T11's: no refund, and neither portions nor seat
come back. As with auto-prep, each order row is locked and its status re-checked
in its own short transaction, so a concurrent Picked Up or cancel wins cleanly and
a repeated run changes nothing. Runs as a caf-worker job.
"""

import uuid
from datetime import datetime, timedelta
from functools import partial

from sqlalchemy.orm import Session

from app.models.enums import OrderStatus
from app.modules.ordering.auto_prep import _NoPayments
from app.modules.ordering.retry import run_in_transaction
from app.modules.ordering.service import OrderService

AUTO_NO_SHOW_REASON = "not collected by end of service"


class AutoNoShowService(OrderService):
    def __init__(self, session: Session) -> None:
        super().__init__(session, _NoPayments())

    def close_uncollected(self, now: datetime) -> int:
        """Move every READY order of a finished service day to NO_SHOW; returns how many."""
        with self.session.begin():
            grace = int(self.repo.get_settings("P-NOSHOW_GRACE_MIN")["P-NOSHOW_GRACE_MIN"])
            due = self.repo.ready_orders_of_days_ended_by(now - timedelta(minutes=grace))
        # One short transaction per order, so one busy order does not hold the others.
        return sum(run_in_transaction(self.session, partial(self._close, oid)) for oid in due)

    def _close(self, order_id: uuid.UUID) -> bool:
        order = self.repo.lock_order(order_id)
        if order.status is not OrderStatus.READY:
            return False  # picked up, or cancelled by the Administrator, meanwhile
        self._move(order, OrderStatus.NO_SHOW, reason=AUTO_NO_SHOW_REASON)
        return True
