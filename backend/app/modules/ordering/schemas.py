import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.models.enums import OrderStatus
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
