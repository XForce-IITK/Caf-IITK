"""US-37 (CAFIITK-162, FR-45, FR-46) acceptance tests TC-US37-AC1..AC2 via
GET /api/v1/admin/orders and GET /api/v1/admin/utilisation.

AC2's "within 30 s" is the dashboard polling every P-POLL; the client test covers
it. Here AC2 checks that the figures the dashboard polls change as bookings do.
"""

import uuid
from datetime import date, datetime, time
from typing import Annotated, Any, cast
from zoneinfo import ZoneInfo

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core import clock
from app.core.security import create_access_token
from app.db.session import get_session
from app.models.capacity import DailyInventory, ServiceDay, Slot
from app.models.catalogue import MenuItem
from app.models.enums import ItemCategory, ItemStatus, Role
from app.models.identity import User
from app.modules.payments.fake import FakePaymentGateway
from app.modules.payments.gateway import PaymentGateway, TransactionGuardedGateway
from app.modules.payments.mockpay_gateway import get_payment_gateway

ORDERS = "/api/v1/admin/orders"
UTILISATION = "/api/v1/admin/utilisation"
IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 10, 6)
NOW = datetime(2026, 10, 6, 9, 0, tzinfo=IST)


def _add(engine: Engine, *rows: Any) -> None:
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add_all(rows)


def _user(engine: Engine, role: Role, name: str = "Asha", email: str | None = None) -> User:
    user = User(
        id=uuid.uuid4(),
        name=name,
        email=email or f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
        password_hash="unused",
        role=role,
    )
    _add(engine, user)
    return user


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


def _slot(day: date, hour: int, minute: int) -> Slot:
    start = datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST)
    return Slot(
        id=uuid.uuid4(),
        service_date=day,
        starts_at=start,
        ends_at=start.replace(minute=minute + 15),
        capacity=30,
    )


@pytest.fixture
def cafe(db_client: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Two slots today (12:00, 12:15), one slot tomorrow, Thali and Tea portions."""
    thali = MenuItem(id=uuid.uuid4(), name="Thali", category=ItemCategory.MEAL, price_paise=8000)
    tea = MenuItem(id=uuid.uuid4(), name="Tea", category=ItemCategory.BEVERAGE, price_paise=1500)
    tomorrow = date(2026, 10, 7)
    days = [
        ServiceDay(
            service_date=d,
            window_start=time(12, 0),
            window_end=time(12, 30),
            slot_len_min=15,
            default_capacity=30,
        )
        for d in (DAY, tomorrow)
    ]
    noon, quarter, next_day = _slot(DAY, 12, 0), _slot(DAY, 12, 15), _slot(tomorrow, 12, 0)
    _add(engine, thali, tea, *days)
    _add(
        engine,
        noon,
        quarter,
        next_day,
        *[
            DailyInventory(item_id=item.id, service_date=d, total=10)
            for item in (thali, tea)
            for d in (DAY, tomorrow)
        ],
    )
    monkeypatch.setattr(clock, "now", lambda: NOW)
    gateway = FakePaymentGateway()

    def guarded(session: Annotated[Session, Depends(get_session)]) -> PaymentGateway:
        return TransactionGuardedGateway(gateway, session)

    cast(FastAPI, db_client.app).dependency_overrides[get_payment_gateway] = guarded
    return {
        "thali": thali,
        "tea": tea,
        "noon": noon,
        "quarter": quarter,
        "next_day": next_day,
        "admin": _auth(_user(engine, Role.ADMIN, "Admin")),
    }


def _place(
    client: TestClient, student: User, slot: Slot, item: MenuItem, qty: int = 1
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/orders",
        json={
            "slot_id": str(slot.id),
            "lines": [{"item_id": str(item.id), "qty": qty}],
            "quoted_payable_paise": item.price_paise * qty,
        },
        headers=_auth(student) | {"Idempotency-Key": uuid.uuid4().hex},
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _cancel(client: TestClient, student: User, order: dict[str, Any]) -> None:
    response = client.post(
        f"/api/v1/orders/{order['id']}/cancel",
        json={"version": order["version"]},
        headers=_auth(student) | {"Idempotency-Key": uuid.uuid4().hex},
    )
    assert response.status_code == 200, response.text


@pytest.fixture
def day_orders(
    db_client: TestClient, engine: Engine, cafe: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    """Two ACCEPTED and one CANCELLED order at 12:15, one ACCEPTED at 12:00, one tomorrow."""
    asha = _user(engine, Role.STUDENT, "Asha Rao", "asha@iitk.ac.in")
    ravi = _user(engine, Role.STUDENT, "Ravi Kumar", "ravi@iitk.ac.in")
    meera = _user(engine, Role.STUDENT, "Meera", "meera_100@iitk.ac.in")
    orders = {
        "asha_quarter": _place(db_client, asha, cafe["quarter"], cafe["thali"]),
        "ravi_quarter": _place(db_client, ravi, cafe["quarter"], cafe["tea"], 2),
        "meera_quarter": _place(db_client, meera, cafe["quarter"], cafe["thali"]),
        "ravi_noon": _place(db_client, ravi, cafe["noon"], cafe["thali"]),
    }
    _cancel(db_client, meera, orders["meera_quarter"])
    # Tomorrow's menu opens tomorrow morning.
    monkeypatch.setattr(clock, "now", lambda: NOW.replace(day=7))
    orders["asha_tomorrow"] = _place(db_client, asha, cafe["next_day"], cafe["tea"])
    monkeypatch.setattr(clock, "now", lambda: NOW)
    return orders


def _ids(response: Any) -> list[str]:
    assert response.status_code == 200, response.text
    return [order["id"] for order in response.json()]


def test_tc_us37_ac1_filter_by_slot_and_state_lists_only_matching_orders(
    db_client: TestClient, cafe: dict[str, Any], day_orders: dict[str, Any]
) -> None:
    response = db_client.get(
        ORDERS,
        params={"date": DAY.isoformat(), "slot_id": str(cafe["quarter"].id), "status": "ACCEPTED"},
        headers=cafe["admin"],
    )

    assert _ids(response) == [day_orders["asha_quarter"]["id"], day_orders["ravi_quarter"]["id"]]
    first = response.json()[0]
    assert (first["status"], first["student_name"], first["student_email"]) == (
        "ACCEPTED",
        "Asha Rao",
        "asha@iitk.ac.in",
    )
    assert first["slot_id"] == str(cafe["quarter"].id)
    assert datetime.fromisoformat(first["slot_starts_at"]) == cafe["quarter"].starts_at
    assert [line["name"] for line in first["price"]["lines"]] == ["Thali"]


def test_without_filters_every_order_of_the_date_is_listed_by_slot_time(
    db_client: TestClient, cafe: dict[str, Any], day_orders: dict[str, Any]
) -> None:
    response = db_client.get(ORDERS, params={"date": DAY.isoformat()}, headers=cafe["admin"])

    assert _ids(response) == [
        day_orders[key]["id"]
        for key in ("ravi_noon", "asha_quarter", "ravi_quarter", "meera_quarter")
    ]


def test_date_defaults_to_the_current_service_date(
    db_client: TestClient, cafe: dict[str, Any], day_orders: dict[str, Any]
) -> None:
    assert len(_ids(db_client.get(ORDERS, headers=cafe["admin"]))) == 4


def test_several_states_can_be_asked_for_together(
    db_client: TestClient, cafe: dict[str, Any], day_orders: dict[str, Any]
) -> None:
    response = db_client.get(
        ORDERS,
        params=[("date", DAY.isoformat()), ("status", "CANCELLED"), ("status", "PREPARING")],
        headers=cafe["admin"],
    )

    assert _ids(response) == [day_orders["meera_quarter"]["id"]]


@pytest.mark.parametrize(
    ("student", "expected"),
    [
        ("RAVI", ["ravi_noon", "ravi_quarter"]),
        ("asha@", ["asha_quarter"]),
        ("rao", ["asha_quarter"]),
        # LIKE wildcards are matched literally, not as patterns.
        ("_100", ["meera_quarter"]),
        ("%", []),
    ],
)
def test_student_filter_matches_part_of_a_name_or_email(
    db_client: TestClient,
    cafe: dict[str, Any],
    day_orders: dict[str, Any],
    student: str,
    expected: list[str],
) -> None:
    response = db_client.get(
        ORDERS, params={"date": DAY.isoformat(), "student": student}, headers=cafe["admin"]
    )

    assert _ids(response) == [day_orders[key]["id"] for key in expected]


def test_limit_caps_the_list(
    db_client: TestClient, cafe: dict[str, Any], day_orders: dict[str, Any]
) -> None:
    response = db_client.get(
        ORDERS, params={"date": DAY.isoformat(), "limit": 1}, headers=cafe["admin"]
    )
    assert _ids(response) == [day_orders["ravi_noon"]["id"]]


@pytest.mark.parametrize(
    "params", [{"status": "LOST"}, {"slot_id": "12:15"}, {"limit": 0}, {"limit": 1001}]
)
def test_invalid_filters_are_422(
    db_client: TestClient, cafe: dict[str, Any], params: dict[str, Any]
) -> None:
    assert db_client.get(ORDERS, params=params, headers=cafe["admin"]).status_code == 422


def test_utilisation_shows_slots_items_and_orders_per_state(
    db_client: TestClient, engine: Engine, cafe: dict[str, Any], day_orders: dict[str, Any]
) -> None:
    coffee = MenuItem(name="Coffee", category=ItemCategory.BEVERAGE, price_paise=2000)
    old = MenuItem(name="Old Dish", category=ItemCategory.MEAL, price_paise=5000)
    gone = MenuItem(name="Gone", category=ItemCategory.SNACK, price_paise=1000)
    _add(engine, coffee, old, gone)
    with Session(engine) as session, session.begin():
        session.get_one(MenuItem, old.id).status = ItemStatus.REMOVED
        session.get_one(MenuItem, gone.id).status = ItemStatus.REMOVED
    _add(engine, DailyInventory(item_id=old.id, service_date=DAY, total=4))

    response = db_client.get(UTILISATION, params={"date": DAY.isoformat()}, headers=cafe["admin"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert datetime.fromisoformat(body["as_of"]) == NOW
    # The cancelled 12:15 order gave its seat back.
    assert [(s["starts_at"][11:16], s["booked"], s["capacity"]) for s in body["slots"]] == [
        ("06:30", 1, 30),
        ("06:45", 2, 30),
    ]
    # An ACTIVE item with no portions set shows 0/0; a removed item shows only if it
    # had portions for the date.
    assert [(i["name"], i["allocated"], i["total"], i["available"]) for i in body["items"]] == [
        ("Coffee", 0, 0, 0),
        ("Old Dish", 0, 4, 4),
        ("Tea", 2, 10, 8),
        ("Thali", 2, 10, 8),
    ]
    counts = body["order_counts"]
    assert (counts["ACCEPTED"], counts["CANCELLED"], counts["PREPARING"]) == (3, 1, 0)
    assert len(counts) == 8


def test_tc_us37_ac2_utilisation_figures_change_as_bookings_change(
    db_client: TestClient, engine: Engine, cafe: dict[str, Any]
) -> None:
    def figures() -> tuple[int, int, int]:
        body = db_client.get(UTILISATION, headers=cafe["admin"]).json()
        [noon] = [s for s in body["slots"] if s["slot_id"] == str(cafe["noon"].id)]
        [thali] = [i for i in body["items"] if i["name"] == "Thali"]
        return noon["booked"], thali["allocated"], body["order_counts"]["ACCEPTED"]

    assert figures() == (0, 0, 0)
    student = _user(engine, Role.STUDENT)
    order = _place(db_client, student, cafe["noon"], cafe["thali"], 3)
    assert figures() == (1, 3, 1)
    _cancel(db_client, student, order)
    assert figures() == (0, 0, 0)


@pytest.mark.parametrize("url", [ORDERS, UTILISATION])
@pytest.mark.parametrize("role", [Role.KITCHEN, Role.STUDENT])
def test_only_the_administrator_sees_the_day(
    db_client: TestClient, engine: Engine, cafe: dict[str, Any], url: str, role: Role
) -> None:
    assert db_client.get(url, headers=_auth(_user(engine, role))).status_code == 403


@pytest.mark.parametrize("url", [ORDERS, UTILISATION])
def test_the_day_view_requires_a_token(db_client: TestClient, url: str) -> None:
    assert db_client.get(url).status_code == 401
