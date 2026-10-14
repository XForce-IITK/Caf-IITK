import uuid
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.agent import Proposal
from app.models.capacity import Slot
from app.models.catalogue import MenuItem
from app.models.enums import OrderStatus, ProposalStatus, ProposalType
from app.models.ordering import Order, OrderLine, OrderTransition


class KitchenRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def unfinished_slots(self, service_date: date, now: datetime, limit: int) -> list[Slot]:
        """The date's slots that have not ended yet, earliest first."""
        return list(
            self.session.scalars(
                select(Slot)
                .where(Slot.service_date == service_date, Slot.ends_at > now)
                .order_by(Slot.starts_at)
                .limit(limit)
            )
        )

    def ended_slots_with_orders(
        self, service_date: date, now: datetime, statuses: tuple[OrderStatus, ...]
    ) -> list[Slot]:
        """The date's slots that have ended but still have orders in `statuses`, earliest first."""
        open_order = select(Order.id).where(Order.slot_id == Slot.id, Order.status.in_(statuses))
        return list(
            self.session.scalars(
                select(Slot)
                .where(
                    Slot.service_date == service_date,
                    Slot.ends_at <= now,
                    open_order.exists(),
                )
                .order_by(Slot.starts_at)
            )
        )

    def orders_in_slots(
        self, slot_ids: list[uuid.UUID], statuses: tuple[OrderStatus, ...]
    ) -> list[tuple[Order, datetime]]:
        """Orders in the slots and statuses, each with its confirmation time.

        The confirmation time is the order's first transition to ACCEPTED, so a
        later modification does not move it back in the queue. Sorted by slot
        start, then confirmation time; the ID breaks ties.
        """
        confirmed_at = (
            select(func.min(OrderTransition.at))
            .where(
                OrderTransition.order_id == Order.id,
                OrderTransition.to_status == OrderStatus.ACCEPTED,
            )
            .scalar_subquery()
        )
        rows = self.session.execute(
            select(Order, confirmed_at)
            .join(Slot, Slot.id == Order.slot_id)
            .where(Order.slot_id.in_(slot_ids), Order.status.in_(statuses))
            .order_by(Slot.starts_at, confirmed_at, Order.id)
        )
        return [(order, at) for order, at in rows]

    def lines_with_names(self, order_ids: list[uuid.UUID]) -> list[tuple[OrderLine, str]]:
        rows = self.session.execute(
            select(OrderLine, MenuItem.name)
            .join(MenuItem, MenuItem.id == OrderLine.item_id)
            .where(OrderLine.order_id.in_(order_ids))
            .order_by(OrderLine.order_id, MenuItem.name)
        )
        return [(line, name) for line, name in rows]

    def approved_prep_priorities(self, slot_ids: list[uuid.UUID]) -> dict[uuid.UUID, Proposal]:
        """Each slot's APPROVED prep-priority proposal; the latest decision if there are several."""
        rows = self.session.scalars(
            select(Proposal)
            .where(
                Proposal.type == ProposalType.PREP_PRIORITY,
                Proposal.status == ProposalStatus.APPROVED,
                Proposal.target_slot_id.in_(slot_ids),
            )
            .order_by(Proposal.decided_at)
        )
        # Later rows overwrite earlier ones, so the most recent approval wins.
        return {proposal.target_slot_id: proposal for proposal in rows if proposal.target_slot_id}
