"""US-10 (CAFIITK-135, FR-12, FR-13) acceptance tests TC-US10-AC1..AC2 via GET /api/v1/menu."""

import uuid
from datetime import date, datetime, time, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core import clock
from app.core.security import create_access_token
from app.models.capacity import DailyInventory, ServiceDay
from app.models.catalogue import MenuItem
from app.models.enums import ItemCategory, ItemStatus, Role
from app.models.identity import User
from app.modules.catalogue.domain import NotOrderableReason, not_orderable_reason

URL = "/api/v1/menu"
D = date(2026, 10, 20)


def _add(engine: Engine, *rows: Any) -> None:
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add_all(rows)


def _headers(engine: Engine, role: Role = Role.STUDENT) -> dict[str, str]:
    user = User(
        id=uuid.uuid4(),
        name=f"{role.value} user",
        email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
        password_hash="unused",
        role=role,
    )
    _add(engine, user)
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


def _service_day(engine: Engine, service_date: date = D) -> None:
    _add(
        engine,
        ServiceDay(
            service_date=service_date,
            window_start=time(12, 0),
            window_end=time(14, 0),
            slot_len_min=15,
            default_capacity=30,
        ),
    )


def _item(
    engine: Engine,
    name: str,
    *,
    total: int | None = None,
    allocated: int = 0,
    service_date: date = D,
    **fields: Any,
) -> MenuItem:
    """A menu item, with a daily_inventory row for `service_date` when `total` is given."""
    item = MenuItem(
        id=uuid.uuid4(),
        name=name,
        category=fields.pop("category", ItemCategory.MEAL),
        price_paise=fields.pop("price_paise", 8000),
        **fields,
    )
    _add(engine, item)
    if total is not None:
        _add(
            engine,
            DailyInventory(
                item_id=item.id, service_date=service_date, total=total, allocated=allocated
            ),
        )
    return item


def _menu(client: TestClient, headers: dict[str, str], day: date | None = D) -> dict[str, Any]:
    response = client.get(URL, params={"date": day.isoformat()} if day else None, headers=headers)
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def _by_name(menu: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["name"]: item for item in menu["items"]}


def test_tc_us10_ac1_active_items_show_their_details(db_client: TestClient, engine: Engine) -> None:
    _service_day(engine)
    thali = _item(engine, "Thali", description="Dal, sabzi, roti, rice", total=50, allocated=8)
    _item(engine, "Tea", category=ItemCategory.BEVERAGE, price_paise=1500, total=100)

    menu = _menu(db_client, _headers(engine))

    assert menu["service_date"] == "2026-10-20"
    assert _by_name(menu)["Thali"] == {
        "id": str(thali.id),
        "name": "Thali",
        "description": "Dal, sabzi, roti, rice",
        "category": "MEAL",
        "price_paise": 8000,
        "available_portions": 42,
        "orderable": True,
        "not_orderable_reason": None,
    }
    tea = _by_name(menu)["Tea"]
    assert (tea["category"], tea["price_paise"], tea["available_portions"]) == (
        "BEVERAGE",
        1500,
        100,
    )


def test_tc_us10_ac2_sold_out_unavailable_and_removed(
    db_client: TestClient, engine: Engine
) -> None:
    _service_day(engine)
    _item(engine, "Thali", total=50)
    _item(engine, "Dosa", total=0)
    _item(engine, "Poha", total=20, unavailable=True, unavailable_reason="Gas ran out")
    _item(engine, "Samosa", total=20, status=ItemStatus.REMOVED)

    items = _by_name(_menu(db_client, _headers(engine)))

    assert set(items) == {"Thali", "Dosa", "Poha"}
    assert (items["Thali"]["orderable"], items["Thali"]["not_orderable_reason"]) == (True, None)
    assert (items["Dosa"]["orderable"], items["Dosa"]["not_orderable_reason"]) == (
        False,
        "SOLD_OUT",
    )
    assert (items["Poha"]["orderable"], items["Poha"]["not_orderable_reason"]) == (
        False,
        "UNAVAILABLE",
    )
    # The flag does not change the portion count (FR-11).
    assert items["Poha"]["available_portions"] == 20


def test_fully_allocated_item_is_sold_out(db_client: TestClient, engine: Engine) -> None:
    _service_day(engine)
    _item(engine, "Thali", total=5, allocated=5)

    [thali] = _menu(db_client, _headers(engine))["items"]

    assert thali["available_portions"] == 0
    assert thali["not_orderable_reason"] == "SOLD_OUT"


def test_item_without_inventory_for_the_date_is_sold_out(
    db_client: TestClient, engine: Engine
) -> None:
    _service_day(engine)
    _service_day(engine, D + timedelta(days=1))
    _item(engine, "Thali", total=50)

    [thali] = _menu(db_client, _headers(engine), D + timedelta(days=1))["items"]

    assert thali["available_portions"] == 0
    assert thali["not_orderable_reason"] == "SOLD_OUT"


def test_date_defaults_to_the_current_service_date(db_client: TestClient, engine: Engine) -> None:
    today = clock.current_service_date()
    _service_day(engine, today)
    _item(engine, "Thali", total=50, service_date=today)

    menu = _menu(db_client, _headers(engine), None)

    assert menu["service_date"] == today.isoformat()
    assert menu["items"][0]["available_portions"] == 50


def test_flag_with_an_end_time_lapses(db_client: TestClient, engine: Engine) -> None:
    _service_day(engine)
    now = clock.now()
    _item(engine, "Dosa", total=10, unavailable=True, unavailable_until=now + timedelta(hours=1))
    _item(engine, "Poha", total=10, unavailable=True, unavailable_until=now - timedelta(hours=1))

    items = _by_name(_menu(db_client, _headers(engine)))

    assert items["Dosa"]["not_orderable_reason"] == "UNAVAILABLE"
    assert items["Poha"]["orderable"] is True


def test_items_are_listed_by_category_then_name(db_client: TestClient, engine: Engine) -> None:
    _item(engine, "tea", category=ItemCategory.BEVERAGE)
    _item(engine, "Thali")
    _item(engine, "dosa")
    _item(engine, "Samosa", category=ItemCategory.SNACK)

    names = [item["name"] for item in _menu(db_client, _headers(engine))["items"]]

    assert names == ["dosa", "Thali", "Samosa", "tea"]


@pytest.mark.parametrize("role", [Role.KITCHEN, Role.ADMIN])
def test_staff_can_browse_the_menu(db_client: TestClient, engine: Engine, role: Role) -> None:
    assert db_client.get(URL, headers=_headers(engine, role)).status_code == 200


def test_menu_requires_a_login(db_client: TestClient) -> None:
    assert db_client.get(URL).status_code == 401


def test_malformed_date_gets_422(db_client: TestClient, engine: Engine) -> None:
    response = db_client.get(URL, params={"date": "20-10-2026"}, headers=_headers(engine))

    assert response.status_code == 422


def test_fr12_orderability_rule() -> None:
    now = datetime(2026, 10, 20, 12, 0, tzinfo=clock.IST)

    def reason(**overrides: Any) -> NotOrderableReason | None:
        facts: dict[str, Any] = {
            "status": ItemStatus.ACTIVE,
            "unavailable": False,
            "unavailable_until": None,
            "available": 1,
            "now": now,
        }
        return not_orderable_reason(**(facts | overrides))

    assert reason() is None
    assert reason(available=0) is NotOrderableReason.SOLD_OUT
    assert reason(unavailable=True) is NotOrderableReason.UNAVAILABLE
    assert reason(unavailable=True, available=0) is NotOrderableReason.UNAVAILABLE
    assert reason(unavailable=True, unavailable_until=now) is None
    assert reason(status=ItemStatus.REMOVED, unavailable=True) is NotOrderableReason.REMOVED
