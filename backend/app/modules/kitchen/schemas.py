import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.models.enums import OrderStatus


class QueueLineOut(BaseModel):
    item_id: uuid.UUID
    name: str
    qty: int


class QueueOrderOut(BaseModel):
    id: uuid.UUID
    status: OrderStatus
    # When the order was first ACCEPTED; the queue is sorted by it within a slot.
    confirmed_at: datetime
    lines: list[QueueLineOut]


class TotalsOrder(StrEnum):
    """How a slot's item totals are ordered (FR-42)."""

    PREP_PRIORITY = "PREP_PRIORITY"  # an approved prep-priority proposal (FR-54)
    COUNT = "COUNT"  # descending count


class SlotQueueOut(BaseModel):
    slot_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    orders: list[QueueOrderOut]
    # Portions still to prepare: ACCEPTED and PREPARING orders, not READY ones.
    item_totals: list[QueueLineOut]
    totals_order: TotalsOrder
    # The approved prep-priority proposal followed, when totals_order is PREP_PRIORITY.
    proposal_id: uuid.UUID | None


class KitchenQueueOut(BaseModel):
    """FR-42: the current slot, then the next one; fewer near the end of service."""

    slots: list[SlotQueueOut]
    # Today's ended slots that still have open orders, earliest first: READY orders
    # waiting to be picked up or marked no-show, and any order left behind.
    earlier_slots: list[SlotQueueOut]


class KitchenAction(StrEnum):
    """The kitchen's buttons (FR-43) and the transitions of Table 4.6-A they ask for."""

    START = "START"  # T5: ACCEPTED -> PREPARING
    READY = "READY"  # T8: PREPARING -> READY
    PICKED_UP = "PICKED_UP"  # T10: READY -> PICKED_UP
    NO_SHOW = "NO_SHOW"  # T11: READY -> NO_SHOW, after slot end + P-NOSHOW_GRACE


class TransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: KitchenAction


class KitchenOrderOut(BaseModel):
    id: uuid.UUID
    status: OrderStatus
    slot_id: uuid.UUID
    # Bumped by every transition, so a Student acting on an older view gets 409 (NFR-5).
    version: int
