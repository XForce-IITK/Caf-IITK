import uuid
from collections import Counter, defaultdict
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.agent import Proposal
from app.models.enums import OrderStatus, ProposalType
from app.modules.kitchen.domain import order_item_totals
from app.modules.kitchen.repository import KitchenRepository
from app.modules.kitchen.schemas import (
    KitchenQueueOut,
    QueueLineOut,
    QueueOrderOut,
    SlotQueueOut,
    TotalsOrder,
)
from app.modules.proposals.payloads import PrepPriorityPayload, parse_payload

# FR-42: the queue shows the current slot and the next one.
QUEUE_SLOTS = 2
QUEUE_STATUSES = (OrderStatus.ACCEPTED, OrderStatus.PREPARING, OrderStatus.READY)
# A READY order is already prepared, so it is listed but not counted in the totals.
TO_PREPARE = frozenset({OrderStatus.ACCEPTED, OrderStatus.PREPARING})


def _priority(proposal: Proposal | None) -> list[uuid.UUID] | None:
    """The proposal's item order, or None if there is none or its payload is malformed."""
    if proposal is None:
        return None
    try:
        payload = parse_payload(ProposalType.PREP_PRIORITY, proposal.payload)
    except ValidationError:
        return None
    assert isinstance(payload, PrepPriorityPayload)
    return payload.item_ids


class KitchenService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = KitchenRepository(session)

    def queue(self, now: datetime) -> KitchenQueueOut:
        """FR-42 / UC-16: the current and next slot's orders and their item totals.

        The current slot is the service date's earliest slot that has not ended:
        the one in progress, or before service the first one. The next slot is the
        one after it.
        """
        with self.session.begin():
            slots = self.repo.unfinished_slots(now.date(), now, QUEUE_SLOTS)
            slot_ids = [slot.id for slot in slots]
            orders = self.repo.orders_in_slots(slot_ids, QUEUE_STATUSES)
            lines = self.repo.lines_with_names([order.id for order, _ in orders])
            proposals = self.repo.approved_prep_priorities(slot_ids)

        lines_by_order: dict[uuid.UUID, list[QueueLineOut]] = defaultdict(list)
        names: dict[uuid.UUID, str] = {}
        for line, name in lines:
            lines_by_order[line.order_id].append(
                QueueLineOut(item_id=line.item_id, name=name, qty=line.qty)
            )
            names[line.item_id] = name

        orders_by_slot: dict[uuid.UUID, list[QueueOrderOut]] = defaultdict(list)
        counts: dict[uuid.UUID, Counter[uuid.UUID]] = defaultdict(Counter)
        for order, confirmed_at in orders:
            order_lines = lines_by_order[order.id]
            orders_by_slot[order.slot_id].append(
                QueueOrderOut(
                    id=order.id,
                    status=order.status,
                    confirmed_at=confirmed_at or order.created_at,
                    lines=order_lines,
                )
            )
            if order.status in TO_PREPARE:
                for order_line in order_lines:
                    counts[order.slot_id][order_line.item_id] += order_line.qty

        result = []
        for slot in slots:
            proposal = proposals.get(slot.id)
            priority = _priority(proposal)
            slot_counts = counts[slot.id]
            result.append(
                SlotQueueOut(
                    slot_id=slot.id,
                    starts_at=slot.starts_at,
                    ends_at=slot.ends_at,
                    orders=orders_by_slot[slot.id],
                    item_totals=[
                        QueueLineOut(item_id=item_id, name=names[item_id], qty=slot_counts[item_id])
                        for item_id in order_item_totals(slot_counts, names, priority)
                    ],
                    totals_order=TotalsOrder.COUNT
                    if priority is None
                    else TotalsOrder.PREP_PRIORITY,
                    proposal_id=None if priority is None or proposal is None else proposal.id,
                )
            )
        return KitchenQueueOut(slots=result)
