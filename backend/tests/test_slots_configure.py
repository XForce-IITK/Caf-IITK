"""US-14 (CAFIITK-139, FR-17) acceptance tests TC-US14-AC1..AC2 via PUT /admin/service-days.

Also covers US-04 AC3 on the real slot-configuration endpoint, and checks that
re-configuring a day never breaks inventory (CAFIITK-136) or existing orders.
"""

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
from app.models.catalogue import MenuItem
from app.models.enums import ItemCategory, OrderStatus, Role
from app.models.identity import User
from app.models.ordering import Order
from app.models.platform import AuditLog, Setting
from app.modules.slots.repository import SlotRepository
from app.modules.slots.service import slot_bounds

IST = ZoneInfo("Asia/Kolkata")
D = date(2026, 10, 6)
URL = f"/api/v1/admin/service-days/{D.isoformat()}"
LUNCH = {
    "window_start": "12:00",
    "window_end": "14:30",
    "slot_len_min": 15,
    "default_capacity": 30,
}


def _user(engine: Engine, role: Role) -> User:
    with Session(engine, expire_on_commit=False) as session, session.begin():
        user = User(
            id=uuid.uuid4(),
            name=f"{role.value} user",
            email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
            password_hash="unused",
            role=role,
        )
        session.add(user)
    return user


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


@pytest.fixture
def admin_user(engine: Engine) -> User:
    return _user(engine, Role.ADMIN)


@pytest.fixture
def admin(admin_user: User) -> dict[str, str]:
    return _auth(admin_user)


def _slots(engine: Engine) -> list[Slot]:
    with Session(engine) as session:
        return list(session.scalars(select(Slot).order_by(Slot.starts_at)))


def _day(engine: Engine) -> ServiceDay | None:
    with Session(engine) as session:
        return session.get(ServiceDay, D)


def test_tc_us14_ac1_window_generates_ten_slots_of_thirty(
    db_client: TestClient, engine: Engine, admin: dict[str, str]
) -> None:
    response = db_client.put(URL, json=LUNCH, headers=admin)

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["slots"]) == 10
    assert all(s["capacity"] == 30 and s["booked"] == 0 for s in body["slots"])
    slots = _slots(engine)
    assert len(slots) == 10
    assert slots[0].starts_at == datetime(2026, 10, 6, 12, 0, tzinfo=IST)
    assert slots[-1].ends_at == datetime(2026, 10, 6, 14, 30, tzinfo=IST)
    # Consecutive, no gaps or overlaps.
    assert all(a.ends_at == b.starts_at for a, b in zip(slots, slots[1:], strict=False))


def test_tc_us14_ac2_slot_length_must_divide_the_window(
    db_client: TestClient, engine: Engine, admin: dict[str, str]
) -> None:
    # 12:00-14:30 is 150 minutes; 20-minute slots do not divide it.
    response = db_client.put(URL, json=LUNCH | {"slot_len_min": 20}, headers=admin)

    assert response.status_code == 422
    assert "does not divide the 150-minute window" in response.text
    assert _day(engine) is None
    assert _slots(engine) == []


def test_slot_length_defaults_to_p_slot_len(
    db_client: TestClient, engine: Engine, admin: dict[str, str]
) -> None:
    body = {k: v for k, v in LUNCH.items() if k != "slot_len_min"}
    with Session(engine) as session, session.begin():
        session.execute(update(Setting).where(Setting.key == "P-SLOT_LEN_MIN").values(value=30))
    try:
        response = db_client.put(URL, json=body, headers=admin)
    finally:
        with Session(engine) as session, session.begin():
            session.execute(update(Setting).where(Setting.key == "P-SLOT_LEN_MIN").values(value=15))

    assert response.status_code == 200
    assert response.json()["slot_len_min"] == 30
    assert len(response.json()["slots"]) == 5


@pytest.mark.parametrize(
    "change",
    [
        {"window_start": "14:30", "window_end": "12:00"},
        {"window_start": "12:00", "window_end": "12:00"},
        {"default_capacity": 0},
        {"default_capacity": 101},
        {"slot_len_min": 0},
        {"window_start": "25:00"},
        {"surprise": True},
    ],
)
def test_invalid_configuration_is_422(
    db_client: TestClient, engine: Engine, admin: dict[str, str], change: dict[str, Any]
) -> None:
    response = db_client.put(URL, json=LUNCH | change, headers=admin)

    assert response.status_code == 422
    assert _slots(engine) == []


@pytest.mark.parametrize("capacity", [1, 100])
def test_capacity_bounds_are_accepted(
    db_client: TestClient, admin: dict[str, str], capacity: int
) -> None:
    response = db_client.put(URL, json=LUNCH | {"default_capacity": capacity}, headers=admin)
    assert response.status_code == 200


def test_reconfiguring_without_orders_regenerates_the_slots(
    db_client: TestClient, engine: Engine, admin: dict[str, str]
) -> None:
    db_client.put(URL, json=LUNCH, headers=admin)
    old_ids = {s.id for s in _slots(engine)}

    new = {
        "window_start": "12:00",
        "window_end": "13:00",
        "slot_len_min": 20,
        "default_capacity": 10,
    }
    response = db_client.put(URL, json=new, headers=admin)

    assert response.status_code == 200
    slots = _slots(engine)
    assert len(slots) == 3
    assert {s.capacity for s in slots} == {10}
    assert old_ids.isdisjoint({s.id for s in slots})
    day = _day(engine)
    assert day is not None
    assert (day.window_end, day.slot_len_min, day.default_capacity) == (time(13, 0), 20, 10)


def _order_on_first_slot(engine: Engine, status: OrderStatus) -> None:
    student = _user(engine, Role.STUDENT)
    first = _slots(engine)[0]
    with Session(engine) as session, session.begin():
        session.add(Order(student_id=student.id, slot_id=first.id, status=status))


@pytest.mark.parametrize("status", [OrderStatus.ACCEPTED, OrderStatus.CANCELLED])
def test_reconfiguring_a_day_with_orders_is_409_and_changes_nothing(
    db_client: TestClient, engine: Engine, admin: dict[str, str], status: OrderStatus
) -> None:
    db_client.put(URL, json=LUNCH, headers=admin)
    before = [(s.id, s.capacity) for s in _slots(engine)]
    # Even a CANCELLED order still points at its slot, so the slot must stay.
    _order_on_first_slot(engine, status)

    response = db_client.put(URL, json=LUNCH | {"default_capacity": 5}, headers=admin)

    assert response.status_code == 409
    assert [(s.id, s.capacity) for s in _slots(engine)] == before
    day = _day(engine)
    assert day is not None
    assert day.default_capacity == 30


def test_order_placed_during_reconfigure_is_caught_by_the_foreign_key(
    db_client: TestClient, engine: Engine, admin: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    db_client.put(URL, json=LUNCH, headers=admin)
    _order_on_first_slot(engine, OrderStatus.ACCEPTED)
    # Simulate the order arriving after our check but before the delete.
    monkeypatch.setattr(SlotRepository, "day_has_orders", lambda self, d: False)

    response = db_client.put(URL, json=LUNCH | {"default_capacity": 5}, headers=admin)

    assert response.status_code == 409
    assert len(_slots(engine)) == 10


def test_reconfiguring_keeps_daily_inventory(
    db_client: TestClient, engine: Engine, admin: dict[str, str]
) -> None:
    # CAFIITK-136 rows reference service_days; the day is updated in place, not replaced.
    db_client.put(URL, json=LUNCH, headers=admin)
    with Session(engine, expire_on_commit=False) as session, session.begin():
        item = MenuItem(name="Thali", category=ItemCategory.MEAL, price_paise=8000)
        session.add(item)
    put = db_client.put(f"/api/v1/admin/inventory/{D}/{item.id}", json={"total": 50}, headers=admin)
    assert put.status_code == 200

    assert (
        db_client.put(URL, json=LUNCH | {"default_capacity": 20}, headers=admin).status_code == 200
    )

    with Session(engine) as session:
        assert session.get(DailyInventory, (item.id, D)) is not None


def test_configuring_a_day_unblocks_inventory(
    db_client: TestClient, engine: Engine, admin: dict[str, str]
) -> None:
    # Before 139, PUT /admin/inventory returned 409 "Service date is not configured".
    with Session(engine, expire_on_commit=False) as session, session.begin():
        item = MenuItem(name="Tea", category=ItemCategory.BEVERAGE, price_paise=1500)
        session.add(item)
    inventory_url = f"/api/v1/admin/inventory/{D}/{item.id}"
    assert db_client.put(inventory_url, json={"total": 10}, headers=admin).status_code == 409

    db_client.put(URL, json=LUNCH, headers=admin)

    assert db_client.put(inventory_url, json={"total": 10}, headers=admin).status_code == 200


def test_configuration_is_audited_with_before_and_after(
    db_client: TestClient, engine: Engine, admin: dict[str, str], admin_user: User
) -> None:
    db_client.put(URL, json=LUNCH, headers=admin)
    db_client.put(URL, json=LUNCH | {"default_capacity": 20}, headers=admin)

    with Session(engine) as session:
        entries = session.scalars(
            select(AuditLog)
            .where(AuditLog.entity_id == D.isoformat(), AuditLog.actor_id == str(admin_user.id))
            .order_by(AuditLog.id)
        ).all()
    assert [e.action for e in entries] == ["SERVICE_DAY_CONFIGURED"] * 2
    first, second = entries
    assert first.before is None
    assert first.actor_id == str(admin_user.id)
    assert first.after == {
        "window_start": "12:00",
        "window_end": "14:30",
        "slot_len_min": 15,
        "default_capacity": 30,
        "slots": 10,
    }
    assert second.before is not None and second.before["default_capacity"] == 30
    assert second.after is not None and second.after["default_capacity"] == 20


@pytest.mark.parametrize("role", [Role.STUDENT, Role.KITCHEN])
def test_tc_us04_ac3_only_the_administrator_configures_slots(
    db_client: TestClient, engine: Engine, role: Role
) -> None:
    # US-04 AC3 (CAFIITK-129) on the real endpoint: a Student token gets 403.
    response = db_client.put(URL, json=LUNCH, headers=_auth(_user(engine, role)))

    assert response.status_code == 403
    assert _day(engine) is None


def test_configuration_requires_a_token(db_client: TestClient, engine: Engine) -> None:
    assert db_client.put(URL, json=LUNCH).status_code == 401
    assert _day(engine) is None


def test_malformed_date_is_422(db_client: TestClient, admin: dict[str, str]) -> None:
    response = db_client.put("/api/v1/admin/service-days/2026-13-40", json=LUNCH, headers=admin)
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("start", "end", "length", "count"),
    [
        (time(12, 0), time(14, 30), 15, 10),
        (time(12, 0), time(12, 15), 15, 1),
        (time(8, 0), time(10, 0), 30, 4),
    ],
)
def test_slot_bounds(start: time, end: time, length: int, count: int) -> None:
    bounds = slot_bounds(D, start, end, length)
    assert len(bounds) == count
    assert bounds[0][0] == datetime.combine(D, start, IST)
    assert bounds[-1][1] == datetime.combine(D, end, IST)
