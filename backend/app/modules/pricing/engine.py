"""Pricing engine (FR-24). A pure function: no database, clock or I/O.

All money is integer paise. The quote endpoint (FR-25) and order placement
(FR-30, which stores the result as the price snapshot, FR-27) both call
`price_cart`, so a quote and the order it becomes are priced identically.
"""

import uuid
from dataclasses import dataclass
from datetime import time

from app.models.enums import DiscountScope, ItemCategory


@dataclass(frozen=True)
class CartLine:
    item_id: uuid.UUID
    category: ItemCategory
    unit_price_paise: int
    qty: int


@dataclass(frozen=True)
class DiscountRule:
    rule_id: uuid.UUID
    start_time: time
    end_time: time
    pct: int
    scope: DiscountScope
    category: ItemCategory | None = None
    item_ids: frozenset[uuid.UUID] = frozenset()

    def covers(self, slot_start: time) -> bool:
        # Half-open [start, end): a rule ending at 12:30 does not cover a 12:30 slot.
        return self.start_time <= slot_start < self.end_time

    def includes(self, line: CartLine) -> bool:
        match self.scope:
            case DiscountScope.ALL:
                return True
            case DiscountScope.CATEGORY:
                return line.category == self.category
            case DiscountScope.ITEMS:
                return line.item_id in self.item_ids


@dataclass(frozen=True)
class SubsidyTerms:
    eligible: bool
    # True if the Student has another subsidised order that day that is not
    # CANCELLED or PAYMENT_FAILED; the subsidy is then 0 (FR-24 step 4).
    already_used_today: bool
    amount_paise: int  # P-SUBSIDY_AMT
    cap_pct: int  # P-SUBSIDY_CAP_PCT


@dataclass(frozen=True)
class PricedLine:
    item_id: uuid.UUID
    unit_price_paise: int
    qty: int
    line_base_paise: int
    rule_id: uuid.UUID | None
    discount_pct: int
    line_discount_paise: int
    line_total_paise: int


@dataclass(frozen=True)
class PriceBreakdown:
    lines: tuple[PricedLine, ...]
    discounted_subtotal_paise: int
    subsidy_paise: int
    rounding_adjustment_paise: int
    payable_paise: int


def percent_of(amount_paise: int, pct: int) -> int:
    """`amount × pct / 100`, rounded half-up to the paisa."""
    return (amount_paise * pct + 50) // 100


def round_to_rupee(amount_paise: int) -> int:
    """Half-up to a whole rupee: 7550 -> 7600, 7549 -> 7500."""
    return (amount_paise + 50) // 100 * 100


def best_rule(line: CartLine, rules: list[DiscountRule], slot_start: time) -> DiscountRule | None:
    """The single highest-percentage rule for this line; rules never stack (FR-24 step 2)."""
    applicable = [r for r in rules if r.covers(slot_start) and r.includes(line)]
    # Ties on percentage are broken by rule id so the choice is deterministic.
    return max(applicable, key=lambda r: (r.pct, str(r.rule_id)), default=None)


def price_cart(
    lines: list[CartLine],
    rules: list[DiscountRule],
    slot_start: time,
    subsidy: SubsidyTerms,
) -> PriceBreakdown:
    """FR-24. `rules` must already be limited to ACTIVE rules; `slot_start` is local (IST)."""
    priced: list[PricedLine] = []
    for line in lines:
        base = line.unit_price_paise * line.qty  # step 1
        rule = best_rule(line, rules, slot_start)  # step 2
        pct = rule.pct if rule else 0
        discount = percent_of(base, pct)
        priced.append(
            PricedLine(
                item_id=line.item_id,
                unit_price_paise=line.unit_price_paise,
                qty=line.qty,
                line_base_paise=base,
                rule_id=rule.rule_id if rule else None,
                discount_pct=pct,
                line_discount_paise=discount,
                line_total_paise=base - discount,
            )
        )

    subtotal = sum(p.line_total_paise for p in priced)  # step 3

    if subsidy.eligible and not subsidy.already_used_today:  # step 4
        subsidy_paise = min(subsidy.amount_paise, percent_of(subtotal, subsidy.cap_pct))
    else:
        subsidy_paise = 0

    before_rounding = subtotal - subsidy_paise  # step 5
    payable = max(0, round_to_rupee(before_rounding))
    return PriceBreakdown(
        lines=tuple(priced),
        discounted_subtotal_paise=subtotal,
        subsidy_paise=subsidy_paise,
        rounding_adjustment_paise=payable - before_rounding,
        payable_paise=payable,
    )
