"""US-19 (FR-24, FR-25) acceptance tests TC-US19-AC1..AC5 through POST /api/v1/quotes."""

import uuid
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.capacity import DailyInventory, ServiceDay, Slot
from app.models.catalogue import DiscountRule, DiscountRuleItem, MenuItem
from app.models.enums import DiscountScope, ItemCategory, OrderStatus, Role
from app.models.identity import User
from app.models.ordering import Order

URL = "/api/v1/quotes"
IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 10, 6)


def _add(engine: Engine, *rows: Any) -> None:
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add_all(rows)


def _user(engine: Engine, role: Role = Role.STUDENT, *, eligible: bool = False) -> User:
    user = User(
        id=uuid.uuid4(),
        name="Asha",
        email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
        password_hash="unused",
        role=role,
        subsidy_eligible=eligible,
    )
    _add(engine, user)
    return user


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


@pytest.fixture
def menu(engine: Engine) -> dict[str, Any]:
    """US-19 AC1 setup: Thali Rs 80, Tea Rs 15, both rules covering the 12:15 slot."""
    thali = MenuItem(id=uuid.uuid4(), name="Thali", category=ItemCategory.MEAL, price_paise=8000)
    tea = MenuItem(id=uuid.uuid4(), name="Tea", category=ItemCategory.BEVERAGE, price_paise=1500)
    day = ServiceDay(
        service_date=DAY,
        window_start=time(12, 0),
        window_end=time(14, 30),
        slot_len_min=15,
        default_capacity=30,
    )
    slot = Slot(
        id=uuid.uuid4(),
        service_date=DAY,
        starts_at=datetime(2026, 10, 6, 12, 15, tzinfo=IST),
        ends_at=datetime(2026, 10, 6, 12, 30, tzinfo=IST),
        capacity=30,
    )
    all_items = DiscountRule(
        id=uuid.uuid4(),
        start_time=time(12, 0),
        end_time=time(13, 0),
        pct=10,
        scope=DiscountScope.ALL,
    )
    beverages = DiscountRule(
        id=uuid.uuid4(),
        start_time=time(12, 0),
        end_time=time(13, 0),
        pct=20,
        scope=DiscountScope.CATEGORY,
        category=ItemCategory.BEVERAGE,
    )
    _add(engine, thali, tea, day)
    _add(
        engine,
        slot,
        all_items,
        beverages,
        DailyInventory(item_id=thali.id, service_date=DAY, total=50),
        DailyInventory(item_id=tea.id, service_date=DAY, total=50),
    )
    return {"thali": thali, "tea": tea, "slot": slot, "all": all_items, "bev": beverages}


def _cart(menu: dict[str, Any]) -> dict[str, Any]:
    return {
        "slot_id": str(menu["slot"].id),
        "lines": [
            {"item_id": str(menu["thali"].id), "qty": 1},
            {"item_id": str(menu["tea"].id), "qty": 2},
        ],
    }


def _subsidised_order(engine: Engine, student: User, slot: Slot) -> uuid.UUID:
    order = Order(
        id=uuid.uuid4(),
        student_id=student.id,
        slot_id=slot.id,
        status=OrderStatus.ACCEPTED,
        subsidy_applied=True,
    )
    _add(engine, order)
    return order.id


def test_tc_us19_ac1_full_breakdown(
    db_client: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    student = _user(engine, eligible=True)

    response = db_client.post(URL, json=_cart(menu), headers=_auth(student))

    assert response.status_code == 200, response.text
    quote = response.json()
    thali_line, tea_line = quote["lines"]
    assert thali_line == {
        "item_id": str(menu["thali"].id),
        "name": "Thali",
        "unit_price_paise": 8000,
        "qty": 1,
        "line_base_paise": 8000,
        "rule_id": str(menu["all"].id),
        "discount_pct": 10,
        "line_discount_paise": 800,
        "line_total_paise": 7200,
    }
    assert (tea_line["discount_pct"], tea_line["line_discount_paise"]) == (20, 600)
    assert tea_line["rule_id"] == str(menu["bev"].id)
    assert quote["discounted_subtotal_paise"] == 9600
    assert quote["subsidy_paise"] == 2000
    assert quote["rounding_adjustment_paise"] == 0
    assert quote["payable_paise"] == 7600


def test_tc_us19_ac2_quote_reserves_nothing(
    db_client: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    student = _user(engine)

    assert db_client.post(URL, json=_cart(menu), headers=_auth(student)).status_code == 200

    with Session(engine) as session:
        allocated = session.scalars(select(DailyInventory.allocated)).all()
        booked = session.scalar(select(Slot.booked).where(Slot.id == menu["slot"].id))
        orders = session.scalars(select(Order)).all()
    assert allocated == [0, 0]
    assert booked == 0
    assert orders == []


def test_tc_us19_ac3_no_second_subsidy_on_the_same_day(
    db_client: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    student = _user(engine, eligible=True)
    _subsidised_order(engine, student, menu["slot"])

    quote = db_client.post(URL, json=_cart(menu), headers=_auth(student)).json()

    assert quote["subsidy_paise"] == 0
    assert quote["payable_paise"] == 9600


def test_tc_us19_ac4_cancelling_the_first_order_frees_the_subsidy(
    db_client: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    student = _user(engine, eligible=True)
    first = _subsidised_order(engine, student, menu["slot"])
    # The cancel endpoint is US-28 (Sprint 2); the state change is what matters here.
    with Session(engine) as session, session.begin():
        session.execute(update(Order).where(Order.id == first).values(status=OrderStatus.CANCELLED))

    quote = db_client.post(URL, json=_cart(menu), headers=_auth(student)).json()

    assert quote["subsidy_paise"] == 2000
    assert quote["payable_paise"] == 7600


def test_payment_failed_order_does_not_use_up_the_subsidy(
    db_client: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    student = _user(engine, eligible=True)
    failed = _subsidised_order(engine, student, menu["slot"])
    with Session(engine) as session, session.begin():
        session.execute(
            update(Order).where(Order.id == failed).values(status=OrderStatus.PAYMENT_FAILED)
        )

    quote = db_client.post(URL, json=_cart(menu), headers=_auth(student)).json()

    assert quote["subsidy_paise"] == 2000


def test_another_students_subsidy_does_not_affect_mine(
    db_client: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    me, other = _user(engine, eligible=True), _user(engine, eligible=True)
    _subsidised_order(engine, other, menu["slot"])

    quote = db_client.post(URL, json=_cart(menu), headers=_auth(me)).json()

    assert quote["subsidy_paise"] == 2000


def test_tc_us19_ac5_payable_rounds_half_up(
    db_client: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    # Rs 75.50 with no discount and no subsidy.
    item = MenuItem(id=uuid.uuid4(), name="Combo", category=ItemCategory.SNACK, price_paise=7550)
    _add(engine, item)
    with Session(engine) as session, session.begin():
        session.execute(update(DiscountRule).values(active=False))
    student = _user(engine)

    body = {"slot_id": str(menu["slot"].id), "lines": [{"item_id": str(item.id), "qty": 1}]}
    quote = db_client.post(URL, json=body, headers=_auth(student)).json()

    assert quote["discounted_subtotal_paise"] == 7550
    assert quote["rounding_adjustment_paise"] == 50
    assert quote["payable_paise"] == 7600


def test_inactive_rule_is_ignored(
    db_client: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    with Session(engine) as session, session.begin():
        session.execute(
            update(DiscountRule).where(DiscountRule.id == menu["bev"].id).values(active=False)
        )
    student = _user(engine)

    quote = db_client.post(URL, json=_cart(menu), headers=_auth(student)).json()

    assert quote["lines"][1]["discount_pct"] == 10  # falls back to "All items 10 %"


@pytest.mark.parametrize("role", [Role.KITCHEN, Role.ADMIN])
def test_only_students_can_quote(
    db_client: TestClient, engine: Engine, menu: dict[str, Any], role: Role
) -> None:
    response = db_client.post(URL, json=_cart(menu), headers=_auth(_user(engine, role)))
    assert response.status_code == 403


def test_quote_requires_a_token(db_client: TestClient, menu: dict[str, Any]) -> None:
    assert db_client.post(URL, json=_cart(menu)).status_code == 401


def test_unknown_slot_is_404(db_client: TestClient, engine: Engine, menu: dict[str, Any]) -> None:
    body = _cart(menu) | {"slot_id": str(uuid.uuid4())}
    response = db_client.post(URL, json=body, headers=_auth(_user(engine)))
    assert response.status_code == 404


def test_removed_or_unknown_items_are_named_in_a_422(
    db_client: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    with Session(engine) as session, session.begin():
        session.execute(
            update(MenuItem).where(MenuItem.id == menu["tea"].id).values(status="REMOVED")
        )
    ghost = uuid.uuid4()
    body = _cart(menu)
    body["lines"].append({"item_id": str(ghost), "qty": 1})

    response = db_client.post(URL, json=body, headers=_auth(_user(engine)))

    assert response.status_code == 422
    assert set(response.json()["detail"]["item_ids"]) == {str(menu["tea"].id), str(ghost)}


def test_quantity_above_max_qty_is_422(
    db_client: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    body = _cart(menu)
    body["lines"][0]["qty"] = 4  # P-MAX_QTY defaults to 3
    response = db_client.post(URL, json=body, headers=_auth(_user(engine)))
    assert response.status_code == 422
    assert "may not exceed 3" in response.text


@pytest.mark.parametrize(
    "lines",
    [
        [],
        [{"item_id": "same", "qty": 1}, {"item_id": "same", "qty": 2}],
        [{"item_id": "x", "qty": 0}],
    ],
)
def test_malformed_cart_is_422(
    db_client: TestClient, engine: Engine, menu: dict[str, Any], lines: list[dict[str, Any]]
) -> None:
    item_id = str(menu["thali"].id)
    for line in lines:
        line["item_id"] = item_id
    body = {"slot_id": str(menu["slot"].id), "lines": lines}
    response = db_client.post(URL, json=body, headers=_auth(_user(engine)))
    assert response.status_code == 422


def test_item_scoped_rule_applies_only_to_listed_items(
    db_client: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    tea_special = DiscountRule(
        id=uuid.uuid4(),
        start_time=time(12, 0),
        end_time=time(13, 0),
        pct=30,
        scope=DiscountScope.ITEMS,
    )
    _add(engine, tea_special)
    _add(engine, DiscountRuleItem(rule_id=tea_special.id, item_id=menu["tea"].id))

    quote = db_client.post(URL, json=_cart(menu), headers=_auth(_user(engine))).json()

    thali_line, tea_line = quote["lines"]
    assert thali_line["discount_pct"] == 10  # "All items 10 %" still wins for Thali
    assert (tea_line["discount_pct"], tea_line["rule_id"]) == (30, str(tea_special.id))
