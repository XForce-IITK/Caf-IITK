import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.core.text import NoNul
from app.models.enums import OrderStatus, PaymentCause, PaymentStatus, Role
from app.models.ordering import Order, OrderTransition, Payment, PriceSnapshot
from app.modules.pricing.schemas import QuoteOut, QuoteRequest


class PlaceOrderRequest(QuoteRequest):
    """The cart and slot that were quoted, plus the amount the Student agreed to (FR-26)."""

    quoted_payable_paise: Annotated[int, Field(ge=0)]


class OrderOut(BaseModel):
    id: uuid.UUID
    status: OrderStatus
    slot_id: uuid.UUID
    version: int
    paid_paise: int
    subsidy_applied: bool
    # The latest price snapshot (FR-27).
    price: QuoteOut
    created_at: datetime

    @classmethod
    def from_rows(cls, order: Order, snapshot: PriceSnapshot) -> "OrderOut":
        return cls(**_order_fields(order, snapshot))


class TransitionOut(BaseModel):
    from_status: OrderStatus | None
    to_status: OrderStatus
    at: datetime
    # Who made the change: a role, or null when the system did. Never a user ID.
    actor_role: Role | None
    reason: str | None


class SnapshotOut(BaseModel):
    """One immutable price snapshot version (FR-27)."""

    version: int
    priced_at: datetime
    price: QuoteOut


class OrderRefundOut(BaseModel):
    amount_paise: int
    # CANCEL, or MODIFY when a cheaper change was refunded the difference.
    cause: PaymentCause
    # PENDING until mockpay acknowledges it; the outbox retries it (FR-39).
    status: PaymentStatus
    at: datetime


class OrderDetailOut(OrderOut):
    """FR-40 and FR-28: the order, every state change so far, every price snapshot
    version and every refund, each oldest first."""

    history: list[TransitionOut]
    snapshots: list[SnapshotOut]
    refunds: list[OrderRefundOut]

    @classmethod
    def from_history(
        cls,
        order: Order,
        snapshots: list[PriceSnapshot],
        transitions: list[OrderTransition],
        refunds: list[Payment],
    ) -> "OrderDetailOut":
        return cls(
            **_order_fields(order, snapshots[-1]),
            snapshots=[
                SnapshotOut(
                    version=row.version,
                    priced_at=row.priced_at,
                    price=QuoteOut.model_validate(row.breakdown),
                )
                for row in snapshots
            ],
            refunds=[
                OrderRefundOut(
                    amount_paise=row.amount_paise,
                    cause=row.cause,
                    status=row.status,
                    at=row.created_at,
                )
                for row in refunds
            ],
            history=[
                TransitionOut(
                    from_status=row.from_status,
                    to_status=row.to_status,
                    at=row.at,
                    actor_role=row.actor_role,
                    reason=row.reason,
                )
                for row in transitions
            ],
        )


def _order_fields(order: Order, snapshot: PriceSnapshot) -> dict[str, object]:
    return {
        "id": order.id,
        "status": order.status,
        "slot_id": order.slot_id,
        "version": order.version,
        "paid_paise": order.paid_paise,
        "subsidy_applied": order.subsidy_applied,
        "price": QuoteOut.model_validate(snapshot.breakdown),
        "created_at": order.created_at,
    }


class CancelOrderRequest(BaseModel):
    """The order version the Student saw when confirming (NFR-5)."""

    version: Annotated[int, Field(ge=1)]


class AdminCancelOrderRequest(CancelOrderRequest):
    """FR-38: the Administrator must say why; whitespace alone is no reason."""

    reason: Annotated[str, Field(min_length=1, max_length=500, pattern=r"\S"), NoNul]


class RefundOut(BaseModel):
    amount_paise: int
    # PENDING until mockpay acknowledges it; the outbox retries it (FR-39).
    status: PaymentStatus


class CancelledOrderOut(OrderOut):
    refund: RefundOut


class ModifyOrderRequest(QuoteRequest):
    """The complete new cart and slot (UC-12), as quoted, and the version the Student saw."""

    version: Annotated[int, Field(ge=1)]
    quoted_payable_paise: Annotated[int, Field(ge=0)]


class ModificationQuoteOut(BaseModel):
    """UC-12 step 3: the new price and its difference from what was paid."""

    quote: QuoteOut
    paid_paise: int
    # Positive: charged on confirmation; negative: refunded.
    difference_paise: int


class ModifiedOrderOut(OrderOut):
    difference_paise: int
    # Present when the modification lowered the price (FR-39).
    refund: RefundOut | None


class AdminOrderOut(OrderOut):
    """FR-45: an order as the Administrator sees it, with who placed it and when it is due."""

    student_id: uuid.UUID
    student_name: str
    student_email: str
    slot_starts_at: datetime


class SlotUtilisationOut(BaseModel):
    slot_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    booked: int
    capacity: int


class ItemUtilisationOut(BaseModel):
    item_id: uuid.UUID
    name: str
    allocated: int
    total: int
    available: int


class UtilisationOut(BaseModel):
    """FR-46: how full each slot and item is on a service date, and orders per state."""

    service_date: date
    # When these figures were read; the dashboard refreshes them every P-POLL.
    as_of: datetime
    slots: list[SlotUtilisationOut]
    items: list[ItemUtilisationOut]
    # Every order state, with 0 for states no order is in.
    order_counts: dict[OrderStatus, int]
