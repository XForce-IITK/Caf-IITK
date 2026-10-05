"""US-16 (CAFIITK-141, FR-19) acceptance tests TC-US16-AC1..AC2 via GET /api/v1/slots.

AC3 (one seat per order, FR-20) is verified with order placement (CAFIITK-147).
"""

import uuid
from datetime import date, datetime, time, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, update
from sqlalchemy.orm import Session

from app.core import clock
from app.core.security import create_access_token
from app.models.capacity import ServiceDay, Slot
from app.models.enums import Role
from app.models.identity import User
from app.models.platform import Setting
from app.modules.slots.domain import NotBookableReason, not_bookable_reason

URL = "/api/v1/slots"
D = date(2026, 10, 20)
# The clock is frozen here; P-BOOK_CLOSE is 15 minutes by default.
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=clock.IST)


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: NOW)


def _headers(engine: Engine, role: Role = Role.STUDENT) -> dict[str, str]:
    user = User(
        id=uuid.uuid4(),
        name=f"{role.value} user",
        email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
        password_hash="unused",
        role=role,
    )
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add(user)
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


def _slot(
    engine: Engine, start: time, *, booked: int = 0, capacity: int = 30, service_date: date = D
) -> Slot:
    """A 15-minute slot; the service day is created with the first slot of a date."""
    starts_at = datetime.combine(service_date, start, clock.IST)
    slot = Slot(
        id=uuid.uuid4(),
        service_date=service_date,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=15),
        capacity=capacity,
        booked=booked,
    )
    with Session(engine, expire_on_commit=False) as session, session.begin():
        if session.get(ServiceDay, service_date) is None:
            session.add(
                ServiceDay(
                    service_date=service_date,
                    window_start=time(12, 0),
                    window_end=time(14, 30),
                    slot_len_min=15,
                    default_capacity=capacity,
                )
            )
            session.flush()
        session.add(slot)
    return slot


def _slots(client: TestClient, headers: dict[str, str], day: date | None = D) -> dict[str, Any]:
    response = client.get(URL, params={"date": day.isoformat()} if day else None, headers=headers)
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def test_tc_us16_ac1_slots_show_remaining_seats_and_full_ones_are_not_bookable(
    db_client: TestClient, engine: Engine
) -> None:
    empty = _slot(engine, time(13, 0))
    _slot(engine, time(13, 15), booked=12)
    _slot(engine, time(13, 30), booked=29)
    _slot(engine, time(13, 45), booked=30)

    body = _slots(db_client, _headers(engine))

    assert body["service_date"] == "2026-10-20"
    first = body["slots"][0]
    assert first["id"] == str(empty.id)
    assert datetime.fromisoformat(first["starts_at"]) == empty.starts_at
    assert datetime.fromisoformat(first["ends_at"]) == empty.ends_at
    assert [
        (s["remaining_seats"], s["bookable"], s["not_bookable_reason"]) for s in body["slots"]
    ] == [(30, True, None), (18, True, None), (1, True, None), (0, False, "FULL")]


def test_tc_us16_ac2_slot_starting_within_book_close_is_not_bookable(
    db_client: TestClient, engine: Engine
) -> None:
    _slot(engine, time(11, 45))  # already started
    _slot(engine, time(12, 0))  # starting now
    _slot(engine, time(12, 14))  # starts in 14 minutes
    _slot(engine, time(12, 15))  # starts in exactly P-BOOK_CLOSE
    _slot(engine, time(12, 16))  # starts in 16 minutes

    slots = _slots(db_client, _headers(engine))["slots"]

    assert [(s["bookable"], s["not_bookable_reason"]) for s in slots] == [
        (False, "CLOSED"),
        (False, "CLOSED"),
        (False, "CLOSED"),
        (False, "CLOSED"),
        (True, None),
    ]
    # Closing a slot does not change its seat count.
    assert {s["remaining_seats"] for s in slots} == {30}


def test_book_close_follows_the_administrator_setting(
    db_client: TestClient, engine: Engine
) -> None:
    _slot(engine, time(12, 16))
    _slot(engine, time(12, 31))
    with Session(engine) as session, session.begin():
        session.execute(update(Setting).where(Setting.key == "P-BOOK_CLOSE_MIN").values(value=30))
    try:
        slots = _slots(db_client, _headers(engine))["slots"]
    finally:
        with Session(engine) as session, session.begin():
            session.execute(
                update(Setting).where(Setting.key == "P-BOOK_CLOSE_MIN").values(value=15)
            )

    assert [s["bookable"] for s in slots] == [False, True]


def test_date_defaults_to_the_current_service_date(db_client: TestClient, engine: Engine) -> None:
    _slot(engine, time(13, 0))
    _slot(engine, time(13, 0), service_date=D + timedelta(days=1))

    body = _slots(db_client, _headers(engine), None)

    assert body["service_date"] == "2026-10-20"
    assert len(body["slots"]) == 1


def test_another_date_lists_only_its_own_slots_in_time_order(
    db_client: TestClient, engine: Engine
) -> None:
    tomorrow = D + timedelta(days=1)
    _slot(engine, time(13, 0))
    _slot(engine, time(12, 30), service_date=tomorrow)
    _slot(engine, time(12, 0), service_date=tomorrow)

    slots = _slots(db_client, _headers(engine), tomorrow)["slots"]

    assert [datetime.fromisoformat(s["starts_at"]) for s in slots] == [
        datetime(2026, 10, 21, 12, 0, tzinfo=clock.IST),
        datetime(2026, 10, 21, 12, 30, tzinfo=clock.IST),
    ]
    assert all(s["bookable"] for s in slots)


def test_date_without_a_service_window_has_no_slots(db_client: TestClient, engine: Engine) -> None:
    assert _slots(db_client, _headers(engine))["slots"] == []


@pytest.mark.parametrize("role", [Role.KITCHEN, Role.ADMIN])
def test_staff_can_view_slots(db_client: TestClient, engine: Engine, role: Role) -> None:
    assert db_client.get(URL, headers=_headers(engine, role)).status_code == 200


def test_slots_require_a_login(db_client: TestClient) -> None:
    assert db_client.get(URL).status_code == 401


def test_malformed_date_gets_422(db_client: TestClient, engine: Engine) -> None:
    response = db_client.get(URL, params={"date": "tomorrow"}, headers=_headers(engine))

    assert response.status_code == 422


def test_fr19_bookable_rule() -> None:
    def reason(**overrides: Any) -> NotBookableReason | None:
        facts: dict[str, Any] = {
            "capacity": 30,
            "booked": 0,
            "starts_at": NOW + timedelta(minutes=16),
            "now": NOW,
            "book_close_min": 15,
        }
        return not_bookable_reason(**(facts | overrides))

    assert reason() is None
    assert reason(booked=29) is None
    assert reason(booked=30) is NotBookableReason.FULL
    assert reason(starts_at=NOW + timedelta(minutes=15)) is NotBookableReason.CLOSED
    assert reason(starts_at=NOW + timedelta(minutes=15), booked=30) is NotBookableReason.CLOSED
    assert reason(book_close_min=0, starts_at=NOW + timedelta(seconds=1)) is None
