import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


class QuoteLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID
    # Upper bound P-MAX_QTY is an admin setting, so the service checks it.
    qty: Annotated[int, Field(ge=1)]


class QuoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot_id: uuid.UUID
    lines: Annotated[list[QuoteLineIn], Field(min_length=1, max_length=20)]

    @field_validator("lines")
    @classmethod
    def _one_line_per_item(cls, lines: list[QuoteLineIn]) -> list[QuoteLineIn]:
        if len({line.item_id for line in lines}) != len(lines):
            raise ValueError("each item may appear only once")
        return lines


class QuoteLineOut(BaseModel):
    item_id: uuid.UUID
    name: str
    unit_price_paise: int
    qty: int
    line_base_paise: int
    rule_id: uuid.UUID | None
    discount_pct: int
    line_discount_paise: int
    line_total_paise: int


class QuoteOut(BaseModel):
    """The full FR-24 breakdown. Amounts are integer paise."""

    slot_id: uuid.UUID
    lines: list[QuoteLineOut]
    discounted_subtotal_paise: int
    subsidy_paise: int
    rounding_adjustment_paise: int
    payable_paise: int
