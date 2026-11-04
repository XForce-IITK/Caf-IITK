"""CAFIITK-187: table-driven and property-based tests of the FR-24 pricing engine.

No database (NFR-38): `price_cart` is a pure function. Hypothesis draws carts,
discount rules, slots and subsidy terms within what the API accepts:
- prices 100-50000 paise (FR-6), at most 20 distinct items per cart;
- rule percentages 1-50 (FR-22) with windows inside the service hours, so
  rules overlap each other and the slot often;
- P-SUBSIDY_AMT 0-50000 paise and P-SUBSIDY_CAP_PCT 0-100 (FR-23).

The strongest property compares every breakdown with `_reference`, a second
implementation of FR-24 written from the SRS text with `Decimal` half-up
rounding; the others pin down one clause each.
"""

import copy
import random
import uuid
from dataclasses import dataclass, replace
from datetime import time
from decimal import ROUND_HALF_UP, Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.enums import DiscountScope, ItemCategory
from app.modules.pricing.engine import (
    CartLine,
    DiscountRule,
    PriceBreakdown,
    SubsidyTerms,
    percent_of,
    price_cart,
)

# deadline=None: a slow CI runner is not a failure.
PROPERTY = settings(max_examples=300, deadline=None)

ITEMS = [uuid.UUID(int=n) for n in range(1, 13)]
# Quarter hours from 11:00 to 15:00: rule windows and slots share these, so
# windows overlap and slots land exactly on window edges.
QUARTERS = [time(h, m) for h in range(11, 15) for m in (0, 15, 30, 45)] + [time(15, 0)]


# --- Reference implementation ---------------------------------------------------------


def _half_up(numerator: int, denominator: int) -> int:
    exact = Decimal(numerator) / Decimal(denominator)
    return int(exact.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _in_scope(rule: DiscountRule, line: CartLine) -> bool:
    if rule.scope is DiscountScope.CATEGORY:
        return rule.category is line.category
    if rule.scope is DiscountScope.ITEMS:
        return line.item_id in rule.item_ids
    return True


@dataclass(frozen=True)
class _Expected:
    pcts: tuple[int, ...]
    line_totals: tuple[int, ...]
    subtotal: int
    subsidy: int
    payable: int


def _reference(
    lines: list[CartLine], rules: list[DiscountRule], slot: time, subsidy: SubsidyTerms
) -> _Expected:
    """FR-24 steps 1-5, as the SRS states them."""
    pcts, totals = [], []
    for line in lines:
        base = line.unit_price_paise * line.qty  # (1)
        pct = max(
            (r.pct for r in rules if r.start_time <= slot < r.end_time and _in_scope(r, line)),
            default=0,
        )  # (2) only the single highest
        pcts.append(pct)
        totals.append(base - _half_up(base * pct, 100))
    subtotal = sum(totals)  # (3)
    granted = 0
    if subsidy.eligible and not subsidy.already_used_today:  # (4)
        granted = min(subsidy.amount_paise, _half_up(subtotal * subsidy.cap_pct, 100))
    payable = max(0, _half_up(subtotal - granted, 100) * 100)  # (5)
    return _Expected(tuple(pcts), tuple(totals), subtotal, granted, payable)


# --- Strategies -----------------------------------------------------------------------


@st.composite
def carts(draw: st.DrawFn) -> list[CartLine]:
    item_ids = draw(st.lists(st.sampled_from(ITEMS), min_size=1, max_size=len(ITEMS), unique=True))
    return [
        CartLine(
            item_id=item_id,
            category=draw(st.sampled_from(ItemCategory)),
            unit_price_paise=draw(st.integers(100, 50_000)),
            qty=draw(st.integers(1, 10)),
        )
        for item_id in item_ids
    ]


@st.composite
def discount_rules(draw: st.DrawFn) -> DiscountRule:
    start, end = sorted(
        draw(st.lists(st.sampled_from(QUARTERS), min_size=2, max_size=2, unique=True))
    )
    scope = draw(st.sampled_from(DiscountScope))
    return DiscountRule(
        rule_id=draw(st.uuids()),
        start_time=start,
        end_time=end,
        # Common percentages as well as any, so equal-percentage rules overlap.
        pct=draw(st.sampled_from([10, 20]) | st.integers(1, 50)),
        scope=scope,
        category=draw(st.sampled_from(ItemCategory)) if scope is DiscountScope.CATEGORY else None,
        item_ids=frozenset(draw(st.lists(st.sampled_from(ITEMS), min_size=1, unique=True)))
        if scope is DiscountScope.ITEMS
        else frozenset(),
    )


subsidies = st.builds(
    SubsidyTerms,
    eligible=st.booleans(),
    already_used_today=st.booleans(),
    amount_paise=st.integers(0, 50_000),
    cap_pct=st.integers(0, 100),
)


@dataclass(frozen=True)
class Scenario:
    lines: list[CartLine]
    rules: list[DiscountRule]
    slot: time
    subsidy: SubsidyTerms

    def price(self, **changes: object) -> PriceBreakdown:
        s = replace(self, **changes)  # type: ignore[arg-type]
        return price_cart(s.lines, s.rules, s.slot, s.subsidy)


@st.composite
def scenarios(draw: st.DrawFn) -> Scenario:
    rules = draw(st.lists(discount_rules(), max_size=6))
    edges = [t for r in rules for t in (r.start_time, r.end_time)]
    on_edge = bool(edges) and draw(st.booleans())
    slot = draw(st.sampled_from(edges if on_edge else QUARTERS))
    return Scenario(draw(carts()), rules, slot, draw(subsidies))


# --- Properties -----------------------------------------------------------------------


@PROPERTY
@given(scenarios())
def test_tc_us19_the_engine_matches_an_independent_reference(s: Scenario) -> None:
    quote = s.price()
    expected = _reference(s.lines, s.rules, s.slot, s.subsidy)

    assert tuple(line.discount_pct for line in quote.lines) == expected.pcts
    assert tuple(line.line_total_paise for line in quote.lines) == expected.line_totals
    assert quote.discounted_subtotal_paise == expected.subtotal
    assert quote.subsidy_paise == expected.subsidy
    assert quote.payable_paise == expected.payable


@PROPERTY
@given(scenarios())
def test_tc_nfr38_identical_inputs_give_identical_outputs(s: Scenario) -> None:
    before = copy.deepcopy(s)

    first, second = s.price(), price_cart(*copy.deepcopy((s.lines, s.rules, s.slot, s.subsidy)))

    assert first == second
    assert s == before  # the inputs are not changed


@PROPERTY
@given(scenarios(), st.randoms(use_true_random=False))
def test_tc_nfr38_the_order_of_rules_and_lines_does_not_change_the_price(
    s: Scenario, rnd: random.Random
) -> None:
    rules, lines = list(s.rules), list(s.lines)
    rnd.shuffle(rules)
    rnd.shuffle(lines)

    original, shuffled = s.price(), s.price(rules=rules, lines=lines)

    by_item = {line.item_id: line for line in original.lines}
    assert all(by_item[line.item_id] == line for line in shuffled.lines)
    assert replace(shuffled, lines=()) == replace(original, lines=())


@PROPERTY
@given(scenarios())
def test_tc_us19_each_line_gets_only_the_highest_covering_rule(s: Scenario) -> None:
    rules_by_id = {rule.rule_id: rule for rule in s.rules}

    for line, priced in zip(s.lines, s.price().lines, strict=True):
        covering = [r for r in s.rules if r.covers(s.slot) and r.includes(line)]
        assert priced.discount_pct == max((r.pct for r in covering), default=0)
        if covering:
            assert priced.rule_id is not None
            assert rules_by_id[priced.rule_id] in covering
        else:
            assert priced.rule_id is None
        # Never stacked: one percentage, at most the 50 % a rule may have.
        assert priced.line_discount_paise == percent_of(priced.line_base_paise, priced.discount_pct)
        assert priced.line_discount_paise <= percent_of(priced.line_base_paise, 50)
        assert priced.line_total_paise == priced.line_base_paise - priced.line_discount_paise


@PROPERTY
@given(discount_rules())
def test_tc_us17_a_rule_covers_its_start_but_not_its_end(rule: DiscountRule) -> None:
    """E28: the window is [start_time, end_time)."""
    assert rule.covers(rule.start_time)
    assert not rule.covers(rule.end_time)


@PROPERTY
@given(scenarios())
def test_tc_us18_the_subsidy_never_exceeds_the_amount_or_the_cap(s: Scenario) -> None:
    quote = s.price()
    subtotal = quote.discounted_subtotal_paise

    assert 0 <= quote.subsidy_paise <= s.subsidy.amount_paise
    assert quote.subsidy_paise <= percent_of(subtotal, s.subsidy.cap_pct) <= subtotal
    if not s.subsidy.eligible or s.subsidy.already_used_today:
        assert quote.subsidy_paise == 0
    else:
        assert quote.subsidy_paise == min(
            s.subsidy.amount_paise, percent_of(subtotal, s.subsidy.cap_pct)
        )


@PROPERTY
@given(scenarios())
def test_tc_us19_payable_is_the_subtotal_less_subsidy_rounded_half_up_to_the_rupee(
    s: Scenario,
) -> None:
    quote = s.price()
    before_rounding = quote.discounted_subtotal_paise - quote.subsidy_paise

    assert quote.payable_paise % 100 == 0
    assert quote.payable_paise == before_rounding + quote.rounding_adjustment_paise
    # Half-up: 50 paise goes up, 49 goes down.
    assert -49 <= quote.rounding_adjustment_paise <= 50


@PROPERTY
@given(
    scenarios(),
    st.integers(0, 10**7),
    # Beyond the 100 % the API allows, to reach the floor.
    st.integers(0, 300),
)
def test_tc_us19_payable_is_never_below_zero(s: Scenario, amount: int, cap: int) -> None:
    generous = SubsidyTerms(
        eligible=True, already_used_today=False, amount_paise=amount, cap_pct=cap
    )
    quote = s.price(subsidy=generous)

    assert quote.payable_paise >= 0
    if quote.subsidy_paise >= quote.discounted_subtotal_paise:
        assert quote.payable_paise == 0


@PROPERTY
@given(scenarios(), discount_rules())
def test_tc_us19_an_extra_discount_rule_never_raises_the_price(
    s: Scenario, extra: DiscountRule
) -> None:
    without, with_extra = s.price(), s.price(rules=[*s.rules, extra])

    assert with_extra.discounted_subtotal_paise <= without.discounted_subtotal_paise
    # Holds through the subsidy: with a cap of at most 100 %, a smaller
    # subtotal never earns so much less subsidy that the total goes up.
    assert with_extra.payable_paise <= without.payable_paise


@PROPERTY
@given(scenarios())
def test_tc_us18_eligibility_never_raises_the_price(s: Scenario) -> None:
    eligible = replace(s.subsidy, eligible=True, already_used_today=False)
    ineligible = replace(s.subsidy, eligible=False)

    assert s.price(subsidy=eligible).payable_paise <= s.price(subsidy=ineligible).payable_paise


# --- Table-driven edges ---------------------------------------------------------------

THALI, TEA, SAMOSA = ITEMS[:3]
NOON_15 = time(12, 15)


def _line(item_id: uuid.UUID, price: int, qty: int = 1) -> CartLine:
    category = ItemCategory.BEVERAGE if item_id == TEA else ItemCategory.MEAL
    return CartLine(item_id, category, price, qty)


def _rule(
    pct: int,
    scope: DiscountScope = DiscountScope.ALL,
    *,
    start: time = time(12, 0),
    end: time = time(13, 0),
    category: ItemCategory | None = None,
    items: frozenset[uuid.UUID] = frozenset(),
) -> DiscountRule:
    return DiscountRule(uuid.uuid4(), start, end, pct, scope, category, items)


def _subsidy(
    amount: int = 2000, cap: int = 50, *, eligible: bool = True, used: bool = False
) -> SubsidyTerms:
    return SubsidyTerms(
        eligible=eligible, already_used_today=used, amount_paise=amount, cap_pct=cap
    )


NONE = _subsidy(eligible=False)
CART = [_line(THALI, 8000), _line(TEA, 1500, 2)]  # Rs 80 + 2 x Rs 15


@pytest.mark.parametrize(
    ("lines", "rules", "slot", "subsidy", "pcts", "subtotal", "granted", "payable"),
    [
        pytest.param(
            CART,
            [_rule(10), _rule(20, DiscountScope.CATEGORY, category=ItemCategory.BEVERAGE)],
            NOON_15,
            _subsidy(),
            (10, 20),
            9600,
            2000,
            7600,
            id="srs-us19-ac1",
        ),
        pytest.param(
            CART,
            [_rule(10), _rule(10)],
            NOON_15,
            NONE,
            (10, 10),
            9900,
            0,
            9900,
            id="tie-applies-once",
        ),
        pytest.param(
            CART,
            [_rule(10), _rule(30, DiscountScope.ITEMS, items=frozenset({THALI}))],
            NOON_15,
            NONE,
            (30, 10),
            8300,
            0,
            8300,
            id="items-rule-beats-all-for-listed-item-only",
        ),
        pytest.param(
            CART,
            [_rule(5, DiscountScope.CATEGORY, category=ItemCategory.SNACK)],
            NOON_15,
            NONE,
            (0, 0),
            11000,
            0,
            11000,
            id="category-rule-for-another-category",
        ),
        pytest.param(
            CART,
            [_rule(10, end=NOON_15)],
            NOON_15,
            NONE,
            (0, 0),
            11000,
            0,
            11000,
            id="rule-ending-at-slot-start",
        ),
        pytest.param(
            CART,
            [_rule(10, start=NOON_15)],
            NOON_15,
            NONE,
            (10, 10),
            9900,
            0,
            9900,
            id="rule-starting-at-slot-start",
        ),
        pytest.param(
            [_line(SAMOSA, 105)],
            [_rule(10)],
            NOON_15,
            NONE,
            (10,),
            94,
            0,
            100,
            id="half-paisa-discount-rounds-up",
        ),
        pytest.param(
            [_line(SAMOSA, 7550)], [], NOON_15, NONE, (0,), 7550, 0, 7600, id="50-paise-rounds-up"
        ),
        pytest.param(
            [_line(SAMOSA, 7549)], [], NOON_15, NONE, (0,), 7549, 0, 7500, id="49-paise-rounds-down"
        ),
        pytest.param(
            [_line(THALI, 8000)],
            [],
            NOON_15,
            _subsidy(5000, 50),
            (0,),
            8000,
            4000,
            4000,
            id="cap-binds",
        ),
        pytest.param(
            [_line(THALI, 8000), _line(TEA, 1500)],
            [],
            NOON_15,
            _subsidy(3000, 10),
            (0, 0),
            9500,
            950,
            8600,
            id="cap-binds-then-rupee-rounding",
        ),
        pytest.param(
            [_line(SAMOSA, 105)],
            [],
            NOON_15,
            _subsidy(2000, 50),
            (0,),
            105,
            53,
            100,
            id="half-paisa-cap-rounds-up",
        ),
        pytest.param(
            [_line(THALI, 8000)], [], NOON_15, _subsidy(cap=0), (0,), 8000, 0, 8000, id="cap-zero"
        ),
        pytest.param(
            [_line(THALI, 8000)],
            [],
            NOON_15,
            _subsidy(amount=0),
            (0,),
            8000,
            0,
            8000,
            id="amount-zero",
        ),
        pytest.param(
            [_line(THALI, 8000)],
            [],
            NOON_15,
            _subsidy(used=True),
            (0,),
            8000,
            0,
            8000,
            id="already-used-today",
        ),
        pytest.param(
            [_line(SAMOSA, 100)],
            [],
            NOON_15,
            _subsidy(2000, 100),
            (0,),
            100,
            100,
            0,
            id="subsidy-covers-everything",
        ),
    ],
)
def test_tc_us19_worked_edges(
    lines: list[CartLine],
    rules: list[DiscountRule],
    slot: time,
    subsidy: SubsidyTerms,
    pcts: tuple[int, ...],
    subtotal: int,
    granted: int,
    payable: int,
) -> None:
    quote = price_cart(lines, rules, slot, subsidy)

    assert tuple(line.discount_pct for line in quote.lines) == pcts
    assert quote.discounted_subtotal_paise == subtotal
    assert quote.subsidy_paise == granted
    assert quote.payable_paise == payable
    assert _reference(lines, rules, slot, subsidy) == _Expected(
        pcts, tuple(line.line_total_paise for line in quote.lines), subtotal, granted, payable
    )
