import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.models.enums import OrderStatus, PaymentStatus, Role
from app.models.ordering import Order, OrderTransition, PriceSnapshot
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


class OrderDetailOut(OrderOut):
    """FR-40: the order and every state change so far, oldest first."""

    history: list[TransitionOut]

    @classmethod
    def from_history(
        cls, order: Order, snapshot: PriceSnapshot, transitions: list[OrderTransition]
    ) -> "OrderDetailOut":
        return cls(
            **_order_fields(order, snapshot),
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


class RefundOut(BaseModel):
    amount_paise: int
    # PENDING until mockpay acknowledges it; the outbox retries it (FR-39).
    status: PaymentStatus


class CancelledOrderOut(OrderOut):
    refund: RefundOut
