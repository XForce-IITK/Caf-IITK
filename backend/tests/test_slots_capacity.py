"""US-15 (CAFIITK-140, FR-18) acceptance test TC-US15-AC1 via PATCH /api/v1/admin/slots/{id}.

AC2 (a reconfiguration may not remove a slot with orders) is in test_slots_configure.py.
"""

import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.capacity import Slot
from app.models.enums import Role
from app.models.identity import User
from app.models.platform import AuditLog

D = date(2026, 10, 6)
LUNCH = {"window_start": "12:00", "window_end": "14:30", "slot_len_min": 15, "default_capacity": 30}


def _url(slot_id: object) -> str:
    return f"/api/v1/admin/slots/{slot_id}"


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
def admin(engine: Engine) -> dict[str, str]:
    return _auth(_user(engine, Role.ADMIN))


@pytest.fixture
def slot(db_client: TestClient, admin: dict[str, str]) -> dict[str, Any]:
    """The first 12:00 slot of a configured day: capacity 30, nothing booked."""
    day = db_client.put(f"/api/v1/admin/service-days/{D}", json=LUNCH, headers=admin)
    assert day.status_code == 200, day.text
    first: dict[str, Any] = day.json()["slots"][0]
    return first


def _book(engine: Engine, slot: dict[str, Any], seats: int) -> None:
    with Session(engine) as session, session.begin():
        session.execute(update(Slot).where(Slot.id == uuid.UUID(slot["id"])).values(booked=seats))


def _stored(engine: Engine, slot: dict[str, Any]) -> tuple[int, int]:
    with Session(engine) as session:
        row = session.get_one(Slot, uuid.UUID(slot["id"]))
        return row.capacity, row.booked


def _audit(engine: Engine, slot: dict[str, Any]) -> list[AuditLog]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(AuditLog)
                .where(AuditLog.entity_type == "slot", AuditLog.entity_id == slot["id"])
                .order_by(AuditLog.id)
            )
        )


def test_tc_us15_ac1_capacity_below_the_booked_seats_is_409_and_unchanged(
    db_client: TestClient, engine: Engine, admin: dict[str, str], slot: dict[str, Any]
) -> None:
    _book(engine, slot, 25)

    response = db_client.patch(_url(slot["id"]), json={"capacity": 20}, headers=admin)

    assert response.status_code == 409
    assert "25 seats booked" in response.text
    assert _stored(engine, slot) == (30, 25)
    assert _audit(engine, slot) == []


@pytest.mark.parametrize("capacity", [25, 40, 100])
def test_capacity_down_to_the_booked_seats_or_up_is_accepted(
    db_client: TestClient,
    engine: Engine,
    admin: dict[str, str],
    slot: dict[str, Any],
    capacity: int,
) -> None:
    _book(engine, slot, 25)

    response = db_client.patch(_url(slot["id"]), json={"capacity": capacity}, headers=admin)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["id"], body["capacity"], body["booked"]) == (slot["id"], capacity, 25)
    assert _stored(engine, slot) == (capacity, 25)


def test_a_cut_waiting_on_a_booking_sees_the_new_seat(
    db_client: TestClient, engine: Engine, admin: dict[str, str], slot: dict[str, Any]
) -> None:
    _book(engine, slot, 25)
    with ThreadPoolExecutor(1) as pool, Session(engine) as booking, booking.begin():
        # A placement holding the slot lock while it books the 26th seat.
        booking.execute(
            update(Slot).where(Slot.id == uuid.UUID(slot["id"])).values(booked=Slot.booked + 1)
        )
        cut = pool.submit(db_client.patch, _url(slot["id"]), json={"capacity": 25}, headers=admin)
        time.sleep(0.5)
        assert not cut.done()  # blocked on the slot lock, not deciding on stale data
        booking.commit()
        response = cut.result(timeout=10)

    assert response.status_code == 409
    assert _stored(engine, slot) == (30, 26)


def test_a_slot_cut_to_its_bookings_shows_as_full(
    db_client: TestClient, engine: Engine, admin: dict[str, str], slot: dict[str, Any]
) -> None:
    _book(engine, slot, 25)
    db_client.patch(_url(slot["id"]), json={"capacity": 25}, headers=admin)

    listed = db_client.get("/api/v1/slots", params={"date": D.isoformat()}, headers=admin).json()

    [first] = [s for s in listed["slots"] if s["id"] == slot["id"]]
    assert first["remaining_seats"] == 0


def test_only_the_changed_slot_is_affected(
    db_client: TestClient, engine: Engine, admin: dict[str, str], slot: dict[str, Any]
) -> None:
    db_client.patch(_url(slot["id"]), json={"capacity": 10}, headers=admin)

    with Session(engine) as session:
        capacities = sorted(session.scalars(select(Slot.capacity)))
    assert capacities == [10] + [30] * 9


def test_change_is_audited_and_repeating_it_writes_nothing(
    db_client: TestClient, engine: Engine, admin: dict[str, str], slot: dict[str, Any]
) -> None:
    _book(engine, slot, 3)
    db_client.patch(_url(slot["id"]), json={"capacity": 12}, headers=admin)
    again = db_client.patch(_url(slot["id"]), json={"capacity": 12}, headers=admin)

    assert again.status_code == 200
    [entry] = _audit(engine, slot)
    assert (entry.action, entry.actor_role) == ("SLOT_CAPACITY_CHANGED", "ADMIN")
    assert (entry.before, entry.after) == (
        {"capacity": 30, "booked": 3},
        {"capacity": 12, "booked": 3},
    )


@pytest.mark.parametrize(
    "body", [{}, {"capacity": 0}, {"capacity": 101}, {"capacity": 20, "booked": 0}]
)
def test_invalid_capacity_is_422(
    db_client: TestClient,
    engine: Engine,
    admin: dict[str, str],
    slot: dict[str, Any],
    body: dict[str, Any],
) -> None:
    assert db_client.patch(_url(slot["id"]), json=body, headers=admin).status_code == 422
    assert _stored(engine, slot) == (30, 0)


def test_unknown_slot_is_404(db_client: TestClient, admin: dict[str, str]) -> None:
    response = db_client.patch(_url(uuid.uuid4()), json={"capacity": 20}, headers=admin)
    assert response.status_code == 404


@pytest.mark.parametrize("role", [Role.KITCHEN, Role.STUDENT])
def test_only_the_administrator_changes_capacity(
    db_client: TestClient, engine: Engine, slot: dict[str, Any], role: Role
) -> None:
    response = db_client.patch(
        _url(slot["id"]), json={"capacity": 20}, headers=_auth(_user(engine, role))
    )

    assert response.status_code == 403
    assert _stored(engine, slot) == (30, 0)


def test_changing_capacity_requires_a_token(
    db_client: TestClient, engine: Engine, slot: dict[str, Any]
) -> None:
    assert db_client.patch(_url(slot["id"]), json={"capacity": 20}).status_code == 401
    assert _stored(engine, slot) == (30, 0)
