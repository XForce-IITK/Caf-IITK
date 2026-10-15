"""US-33 (CAFIITK-158, FR-42, FR-54) acceptance tests TC-US33-AC1..AC2 via
GET /api/v1/kitchen/queue.

Orders and their ACCEPTED transitions are inserted directly, so each test controls
the confirmation times. For AC2 the approved prep-priority proposal is inserted
directly too, in the payload shape of `app.modules.proposals.payloads`; approving
through the API arrives with CAFIITK-165.
"""

import uuid
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core import clock
from app.core.security import create_access_token
from app.models.agent import AgentRun, Proposal
from app.models.capacity import ServiceDay, Slot
from app.models.catalogue import MenuItem
from app.models.enums import (
    AgentRunStatus,
    AgentSource,
    AgentTrigger,
    ItemCategory,
    OrderStatus,
    ProposalStatus,
    ProposalType,
    Role,
)
from app.models.identity import User
from app.models.ordering import Order, OrderLine, OrderTransition
from app.modules.kitchen.domain import order_item_totals

QUEUE = "/api/v1/kitchen/queue"
IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 10, 6)
# Inside the 12:00 slot, so it is the current slot and 12:15 the next.
NOW = datetime(2026, 10, 6, 12, 5, tzinfo=IST)


def _at(hour: int, minute: int, day: date = DAY) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=IST)


def _add(engine: Engine, *rows: Any) -> None:
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add_all(rows)


def _user(engine: Engine, role: Role) -> User:
    user = User(
        id=uuid.uuid4(),
        name=f"{role.value} user",
        email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
        password_hash="unused",
        role=role,
    )
    _add(engine, user)
    return user


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


@pytest.fixture
def api(db_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(clock, "now", lambda: NOW)
    return db_client


@pytest.fixture
def kitchen(engine: Engine) -> dict[str, str]:
    return _auth(_user(engine, Role.KITCHEN))


@pytest.fixture
def student(engine: Engine) -> User:
    return _user(engine, Role.STUDENT)


@pytest.fixture
def menu(engine: Engine) -> dict[str, Any]:
    """Four 15-minute slots from 12:00, one slot the day before, and three items."""
    items = {
        name: MenuItem(id=uuid.uuid4(), name=name, category=ItemCategory.MEAL, price_paise=5000)
        for name in ("Thali", "Dosa", "Chai")
    }
    days = [
        ServiceDay(
            service_date=day,
            window_start=time(12, 0),
            window_end=time(13, 0),
            slot_len_min=15,
            default_capacity=30,
        )
        for day in (DAY - timedelta(days=1), DAY)
    ]
    slots = {
        start: Slot(
            id=uuid.uuid4(),
            service_date=DAY,
            starts_at=_at(12, start),
            ends_at=_at(12, start) + timedelta(minutes=15),
            capacity=30,
        )
        for start in (0, 15, 30, 45)
    }
    yesterday = Slot(
        id=uuid.uuid4(),
        service_date=DAY - timedelta(days=1),
        starts_at=_at(12, 15, DAY - timedelta(days=1)),
        ends_at=_at(12, 30, DAY - timedelta(days=1)),
        capacity=30,
    )
    _add(engine, *items.values(), *days)
    _add(engine, *slots.values(), yesterday)
    return {"items": items, "slots": slots, "yesterday": yesterday}


def _order(
    engine: Engine,
    student: User,
    slot: Slot,
    status: OrderStatus,
    confirmed_at: datetime | None,
    lines: dict[MenuItem, int],
) -> uuid.UUID:
    """An order in `status`, ACCEPTED at `confirmed_at` (None: never accepted)."""
    order = Order(id=uuid.uuid4(), student_id=student.id, slot_id=slot.id, status=status)
    rows: list[Any] = [order]
    rows += [OrderLine(order_id=order.id, item_id=item.id, qty=qty) for item, qty in lines.items()]
    if confirmed_at is not None:
        rows.append(
            OrderTransition(
                order_id=order.id,
                from_status=OrderStatus.PENDING_PAYMENT,
                to_status=OrderStatus.ACCEPTED,
                at=confirmed_at,
            )
        )
    _add(engine, order)
    _add(engine, *rows[1:])
    return order.id


def _approve_prep_priority(
    engine: Engine, slot: Slot, item_ids: list[uuid.UUID], decided_at: datetime
) -> uuid.UUID:
    # Requested by a user, so the db_client clean-up's TRUNCATE users cascades to it.
    run = AgentRun(
        id=uuid.uuid4(),
        trigger=AgentTrigger.ON_DEMAND,
        requested_by=_user(engine, Role.ADMIN).id,
        status=AgentRunStatus.SUCCEEDED,
        source=AgentSource.LLM,
    )
    proposal = Proposal(
        id=uuid.uuid4(),
        run_id=run.id,
        type=ProposalType.PREP_PRIORITY,
        target_date=DAY,
        target_slot_id=slot.id,
        payload={"item_ids": [str(item_id) for item_id in item_ids]},
        rationale="Dosa batter takes longest",
        source=AgentSource.LLM,
        status=ProposalStatus.APPROVED,
        expires_at=slot.starts_at,
        decided_at=decided_at,
    )
    _add(engine, run)
    _add(engine, proposal)
    return proposal.id


def _queue(api: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = api.get(QUEUE, headers=headers)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _totals(slot: dict[str, Any]) -> list[tuple[str, int]]:
    return [(line["name"], line["qty"]) for line in slot["item_totals"]]


def test_tc_us33_ac1_only_active_orders_of_current_and_next_slot_in_order(
    api: TestClient, engine: Engine, kitchen: dict[str, str], student: User, menu: dict[str, Any]
) -> None:
    thali, dosa = menu["items"]["Thali"], menu["items"]["Dosa"]
    slots = menu["slots"]
    current, nxt = slots[0], slots[15]
    # Shown, in this order: by slot, then by confirmation time, not by insertion.
    current_late = _order(engine, student, current, OrderStatus.READY, _at(9, 30), {thali: 1})
    current_early = _order(engine, student, current, OrderStatus.PREPARING, _at(9, 10), {dosa: 2})
    next_late = _order(engine, student, nxt, OrderStatus.ACCEPTED, _at(10, 0), {thali: 2})
    next_early = _order(engine, student, nxt, OrderStatus.ACCEPTED, _at(8, 45), {dosa: 1})
    # Not shown: finished or never accepted, a later slot, another day.
    for status in (
        OrderStatus.PICKED_UP,
        OrderStatus.NO_SHOW,
        OrderStatus.CANCELLED,
    ):
        _order(engine, student, current, status, _at(8, 30), {thali: 5})
    _order(engine, student, nxt, OrderStatus.PENDING_PAYMENT, None, {thali: 5})
    _order(engine, student, nxt, OrderStatus.PAYMENT_FAILED, None, {thali: 5})
    _order(engine, student, slots[30], OrderStatus.ACCEPTED, _at(8, 0), {thali: 5})
    _order(engine, student, menu["yesterday"], OrderStatus.ACCEPTED, _at(8, 0), {thali: 5})

    body = _queue(api, kitchen)

    assert [slot["slot_id"] for slot in body["slots"]] == [str(current.id), str(nxt.id)]
    shown = [[order["id"] for order in slot["orders"]] for slot in body["slots"]]
    assert shown == [
        [str(current_early), str(current_late)],
        [str(next_early), str(next_late)],
    ]
    first = body["slots"][0]["orders"][0]
    assert first["status"] == "PREPARING"
    assert datetime.fromisoformat(first["confirmed_at"]) == _at(9, 10)
    assert first["lines"] == [{"item_id": str(dosa.id), "name": "Dosa", "qty": 2}]
    # The READY Thali is already cooked, so only the PREPARING Dosa is left to make.
    assert _totals(body["slots"][0]) == [("Dosa", 2)]
    assert _totals(body["slots"][1]) == [("Thali", 2), ("Dosa", 1)]


def test_tc_us33_ac1_current_slot_moves_on_when_a_slot_ends(
    api: TestClient,
    engine: Engine,
    kitchen: dict[str, str],
    student: User,
    menu: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slots = menu["slots"]
    thali = menu["items"]["Thali"]
    _order(engine, student, slots[0], OrderStatus.READY, _at(9, 0), {thali: 1})

    monkeypatch.setattr(clock, "now", lambda: _at(11, 0))
    before_service = _queue(api, kitchen)["slots"]
    monkeypatch.setattr(clock, "now", lambda: _at(12, 15))
    after_first_slot = _queue(api, kitchen)["slots"]
    monkeypatch.setattr(clock, "now", lambda: _at(12, 50))
    last_slot = _queue(api, kitchen)["slots"]
    monkeypatch.setattr(clock, "now", lambda: _at(13, 0))
    after_service = _queue(api, kitchen)["slots"]

    def ids(*starts: int) -> list[str]:
        return [str(slots[start].id) for start in starts]

    assert [slot["slot_id"] for slot in before_service] == ids(0, 15)
    assert len(before_service[0]["orders"]) == 1
    assert [slot["slot_id"] for slot in after_first_slot] == ids(15, 30)
    assert [slot["slot_id"] for slot in last_slot] == ids(45)
    assert after_service == []


def test_ended_slots_with_open_orders_stay_listed_for_pickup_and_no_show(
    api: TestClient,
    engine: Engine,
    kitchen: dict[str, str],
    student: User,
    menu: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A READY order can be marked no-show only after its slot ends (FR-43), so the
    queue keeps today's ended slots that still have open orders."""
    slots = menu["slots"]
    thali = menu["items"]["Thali"]
    ready = _order(engine, student, slots[0], OrderStatus.READY, _at(9, 0), {thali: 1})
    _order(engine, student, slots[15], OrderStatus.PICKED_UP, _at(9, 0), {thali: 1})
    _order(engine, student, slots[30], OrderStatus.ACCEPTED, _at(9, 0), {thali: 2})
    monkeypatch.setattr(clock, "now", lambda: _at(12, 35))

    body = _queue(api, kitchen)

    assert [slot["slot_id"] for slot in body["slots"]] == [
        str(slots[30].id),
        str(slots[45].id),
    ]
    # The 12:15 slot ended with nothing open, so only the 12:00 slot is listed.
    [earlier] = body["earlier_slots"]
    assert earlier["slot_id"] == str(slots[0].id)
    assert [order["id"] for order in earlier["orders"]] == [str(ready)]
    assert earlier["item_totals"] == []

    monkeypatch.setattr(clock, "now", lambda: _at(11, 0))
    assert _queue(api, kitchen)["earlier_slots"] == []


def test_tc_us33_ac2_next_slot_totals_follow_the_approved_prep_priority(
    api: TestClient, engine: Engine, kitchen: dict[str, str], student: User, menu: dict[str, Any]
) -> None:
    thali, dosa, chai = (menu["items"][name] for name in ("Thali", "Dosa", "Chai"))
    current, nxt = menu["slots"][0], menu["slots"][15]
    for slot in (current, nxt):
        _order(engine, student, slot, OrderStatus.ACCEPTED, _at(9, 0), {thali: 3, chai: 2})
        _order(engine, student, slot, OrderStatus.ACCEPTED, _at(9, 5), {dosa: 1})
    # An older approval for the same slot is superseded by the later one.
    _approve_prep_priority(engine, nxt, [thali.id, chai.id, dosa.id], _at(10, 0))
    proposal_id = _approve_prep_priority(engine, nxt, [dosa.id, chai.id], _at(11, 0))

    current_queue, next_queue = _queue(api, kitchen)["slots"]

    # The approved order first; Thali, which it does not name, after it by count.
    assert _totals(next_queue) == [("Dosa", 1), ("Chai", 2), ("Thali", 3)]
    assert next_queue["totals_order"] == "PREP_PRIORITY"
    assert next_queue["proposal_id"] == str(proposal_id)
    # The other slot has no approved proposal: descending count.
    assert _totals(current_queue) == [("Thali", 3), ("Chai", 2), ("Dosa", 1)]
    assert current_queue["totals_order"] == "COUNT"
    assert current_queue["proposal_id"] is None


def test_tc_us33_ac2_only_an_approved_prep_priority_counts(
    api: TestClient, engine: Engine, kitchen: dict[str, str], student: User, menu: dict[str, Any]
) -> None:
    thali, dosa = menu["items"]["Thali"], menu["items"]["Dosa"]
    nxt = menu["slots"][15]
    _order(engine, student, nxt, OrderStatus.ACCEPTED, _at(9, 0), {thali: 3, dosa: 1})
    pending = _approve_prep_priority(engine, nxt, [dosa.id, thali.id], _at(10, 0))
    with Session(engine) as session, session.begin():
        proposal = session.get(Proposal, pending)
        assert proposal is not None
        proposal.status = ProposalStatus.PENDING

    next_queue = _queue(api, kitchen)["slots"][1]

    assert _totals(next_queue) == [("Thali", 3), ("Dosa", 1)]
    assert next_queue["totals_order"] == "COUNT"


def test_a_malformed_approved_payload_falls_back_to_count(
    api: TestClient, engine: Engine, kitchen: dict[str, str], student: User, menu: dict[str, Any]
) -> None:
    thali, dosa = menu["items"]["Thali"], menu["items"]["Dosa"]
    nxt = menu["slots"][15]
    _order(engine, student, nxt, OrderStatus.ACCEPTED, _at(9, 0), {thali: 3, dosa: 1})
    proposal_id = _approve_prep_priority(engine, nxt, [dosa.id], _at(10, 0))
    with Session(engine) as session, session.begin():
        proposal = session.get(Proposal, proposal_id)
        assert proposal is not None
        proposal.payload = {"items": "not the agreed shape"}

    next_queue = _queue(api, kitchen)["slots"][1]

    assert _totals(next_queue) == [("Thali", 3), ("Dosa", 1)]
    assert next_queue["totals_order"] == "COUNT"
    assert next_queue["proposal_id"] is None


def test_admin_sees_the_queue_and_student_is_denied(
    api: TestClient, engine: Engine, student: User, menu: dict[str, Any]
) -> None:
    assert api.get(QUEUE, headers=_auth(_user(engine, Role.ADMIN))).status_code == 200
    assert api.get(QUEUE, headers=_auth(student)).status_code == 403
    assert api.get(QUEUE).status_code == 401


def test_order_item_totals_rules() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    names = {a: "Aloo", b: "Bhaji", c: "Chai"}

    # Descending count; equal counts by name.
    assert order_item_totals({a: 1, b: 4, c: 1}, names, None) == [b, a, c]
    # Listed first in the given order; a listed item with no demand is left out;
    # a repeated ID counts once.
    assert order_item_totals({a: 1, b: 4}, names, [c, a, a]) == [a, b]
    assert order_item_totals({}, names, [a]) == []
