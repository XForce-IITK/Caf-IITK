import uuid
from datetime import datetime, time
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.core.text import NoNul
from app.models.enums import DiscountScope, ItemCategory

# FR-22: 1-50 %. Mirrors the discount_rules pct_range CHECK.
MIN_DISCOUNT_PCT = 1
MAX_DISCOUNT_PCT = 50
# An ITEMS rule lists at most the whole catalogue (30 active items, SRS 1.3).
MAX_RULE_ITEMS = 30


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


def _wall_clock(value: time) -> time:
    if value.tzinfo is not None:
        raise ValueError("give an IST wall-clock time without a UTC offset")
    return value


# Discount-rule times are IST wall-clock, like slot times (SRS Table 4.0-B).
WallClock = Annotated[time, AfterValidator(_wall_clock)]
RuleName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60), NoNul
]
RulePct = Annotated[int, Field(ge=MIN_DISCOUNT_PCT, le=MAX_DISCOUNT_PCT)]
RuleItems = Annotated[list[uuid.UUID], Field(max_length=MAX_RULE_ITEMS)]


def _distinct(item_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    if len(set(item_ids)) != len(item_ids):
        raise ValueError("each item may appear only once")
    return item_ids


class DiscountRuleCreate(BaseModel):
    """FR-22. A slot is discounted when its start is in [start_time, end_time).

    `category` is required for a CATEGORY rule and `item_ids` for an ITEMS rule;
    each is refused for any other scope.
    """

    model_config = ConfigDict(extra="forbid")

    name: RuleName
    start_time: WallClock
    end_time: WallClock
    pct: RulePct
    scope: DiscountScope
    category: ItemCategory | None = None
    item_ids: Annotated[RuleItems, AfterValidator(_distinct)] = []


class DiscountRuleUpdate(BaseModel):
    """FR-22: change any of a rule's fields, or deactivate (and reactivate) it.

    Changing `scope` clears `category` and `item_ids` unless they are given too.
    """

    model_config = ConfigDict(extra="forbid")

    name: RuleName | None = None
    start_time: WallClock | None = None
    end_time: WallClock | None = None
    pct: RulePct | None = None
    scope: DiscountScope | None = None
    category: ItemCategory | None = None
    item_ids: Annotated[RuleItems, AfterValidator(_distinct)] | None = None
    active: bool | None = None

    @model_validator(mode="after")
    def _at_least_one_field_and_no_nulls(self) -> "DiscountRuleUpdate":
        if not self.model_fields_set:
            raise ValueError("give at least one field to change")
        # A null category is how a rule stops being a CATEGORY rule; nothing else is nullable.
        nulls = sorted(
            name for name in self.model_fields_set - {"category"} if getattr(self, name) is None
        )
        if nulls:
            raise ValueError(f"{', '.join(nulls)} cannot be null")
        return self


class DiscountRuleOut(BaseModel):
    id: uuid.UUID
    name: str
    start_time: time
    end_time: time
    pct: int
    scope: DiscountScope
    category: ItemCategory | None
    item_ids: list[uuid.UUID]
    active: bool
    created_at: datetime
