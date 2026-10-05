"""FR-24 pricing engine: TC-US19-AC1 and AC5 at unit level, plus the rule edges."""

import uuid
from datetime import time

import pytest

from app.models.enums import DiscountScope, ItemCategory
from app.modules.pricing.engine import (
    CartLine,
    DiscountRule,
    SubsidyTerms,
    percent_of,
    price_cart,
    round_to_rupee,
)

THALI = uuid.uuid4()
TEA = uuid.uuid4()
NOON_15 = time(12, 15)

NO_SUBSIDY = SubsidyTerms(eligible=False, already_used_today=False, amount_paise=2000, cap_pct=50)
ELIGIBLE = SubsidyTerms(eligible=True, already_used_today=False, amount_paise=2000, cap_pct=50)


def rule(
    pct: int,
    scope: DiscountScope = DiscountScope.ALL,
    *,
    start: time = time(12, 0),
    end: time = time(13, 0),
    category: ItemCategory | None = None,
    items: frozenset[uuid.UUID] = frozenset(),
) -> DiscountRule:
    return DiscountRule(uuid.uuid4(), start, end, pct, scope, category, items)


def thali(qty: int = 1) -> CartLine:
    return CartLine(THALI, ItemCategory.MEAL, 8000, qty)


def tea(qty: int = 2) -> CartLine:
    return CartLine(TEA, ItemCategory.BEVERAGE, 1500, qty)


def test_tc_us19_ac1_worked_example() -> None:
    all_items = rule(10)
    beverages = rule(20, DiscountScope.CATEGORY, category=ItemCategory.BEVERAGE)

    quote = price_cart([thali(), tea()], [all_items, beverages], NOON_15, ELIGIBLE)

    thali_line, tea_line = quote.lines
    assert (thali_line.line_discount_paise, thali_line.discount_pct) == (800, 10)
    assert thali_line.rule_id == all_items.rule_id
    # 20 % only, not 10 % + 20 %: rules never stack.
    assert (tea_line.line_discount_paise, tea_line.discount_pct) == (600, 20)
    assert tea_line.rule_id == beverages.rule_id
    assert quote.discounted_subtotal_paise == 9600
    assert quote.subsidy_paise == 2000
    assert quote.payable_paise == 7600


def test_tc_us19_ac5_payable_rounds_half_up_to_the_rupee() -> None:
    # Rs 75.50 discounted subtotal, no subsidy -> Rs 76.
    line = CartLine(THALI, ItemCategory.MEAL, 7550, 1)
    quote = price_cart([line], [], NOON_15, NO_SUBSIDY)
    assert quote.discounted_subtotal_paise == 7550
    assert quote.payable_paise == 7600
    assert quote.rounding_adjustment_paise == 50


def test_just_below_half_rounds_down() -> None:
    quote = price_cart([CartLine(THALI, ItemCategory.MEAL, 7549, 1)], [], NOON_15, NO_SUBSIDY)
    assert quote.payable_paise == 7500
    assert quote.rounding_adjustment_paise == -49


def test_line_discount_rounds_half_up_to_the_paisa() -> None:
    # 1 x Rs 1.05 at 10 % = 10.5 paise -> 11 paise.
    quote = price_cart(
        [CartLine(THALI, ItemCategory.SNACK, 105, 1)], [rule(10)], NOON_15, NO_SUBSIDY
    )
    assert quote.lines[0].line_discount_paise == 11


def test_no_rule_means_no_discount() -> None:
    quote = price_cart([thali()], [], NOON_15, NO_SUBSIDY)
    line = quote.lines[0]
    assert (line.rule_id, line.discount_pct, line.line_discount_paise) == (None, 0, 0)
    assert quote.payable_paise == 8000


@pytest.mark.parametrize(
    ("slot_start", "applies"),
    [(time(11, 45), False), (time(12, 0), True), (time(12, 15), True), (time(12, 30), False)],
)
def test_rule_covers_slot_start_half_open(slot_start: time, applies: bool) -> None:
    early_bird = rule(20, start=time(12, 0), end=time(12, 30))
    quote = price_cart([thali()], [early_bird], slot_start, NO_SUBSIDY)
    assert (quote.lines[0].discount_pct == 20) is applies


def test_category_rule_skips_other_categories() -> None:
    beverages = rule(20, DiscountScope.CATEGORY, category=ItemCategory.BEVERAGE)
    quote = price_cart([thali(), tea()], [beverages], NOON_15, NO_SUBSIDY)
    assert [line.discount_pct for line in quote.lines] == [0, 20]


def test_items_rule_applies_only_to_listed_items() -> None:
    tea_only = rule(30, DiscountScope.ITEMS, items=frozenset({TEA}))
    quote = price_cart([thali(), tea()], [tea_only], NOON_15, NO_SUBSIDY)
    assert [line.discount_pct for line in quote.lines] == [0, 30]


def test_highest_rule_wins_regardless_of_order() -> None:
    low, high = rule(10), rule(25)
    for rules in ([low, high], [high, low]):
        quote = price_cart([thali()], rules, NOON_15, NO_SUBSIDY)
        assert quote.lines[0].rule_id == high.rule_id


def test_subsidy_is_capped_at_a_percentage_of_the_subtotal() -> None:
    # Rs 30 subtotal, cap 50 % = Rs 15 < Rs 20 flat subsidy.
    quote = price_cart([tea()], [], NOON_15, ELIGIBLE)
    assert quote.subsidy_paise == 1500
    assert quote.payable_paise == 1500


def test_subsidy_zero_when_not_eligible() -> None:
    assert price_cart([thali()], [], NOON_15, NO_SUBSIDY).subsidy_paise == 0


def test_subsidy_zero_when_already_used_today() -> None:
    used = SubsidyTerms(eligible=True, already_used_today=True, amount_paise=2000, cap_pct=50)
    assert price_cart([thali()], [], NOON_15, used).subsidy_paise == 0


def test_payable_never_below_zero() -> None:
    generous = SubsidyTerms(
        eligible=True, already_used_today=False, amount_paise=10**6, cap_pct=100
    )
    quote = price_cart([thali()], [], NOON_15, generous)
    assert quote.payable_paise == 0


@pytest.mark.parametrize(
    ("amount", "pct", "expected"), [(800, 10, 80), (105, 10, 11), (104, 10, 10), (0, 50, 0)]
)
def test_percent_of(amount: int, pct: int, expected: int) -> None:
    assert percent_of(amount, pct) == expected


@pytest.mark.parametrize(
    ("amount", "expected"), [(0, 0), (49, 0), (50, 100), (7550, 7600), (7600, 7600)]
)
def test_round_to_rupee(amount: int, expected: int) -> None:
    assert round_to_rupee(amount) == expected
