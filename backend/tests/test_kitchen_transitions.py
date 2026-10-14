"""US-34 (FR-29, FR-43) acceptance tests TC-US34-AC1..AC4 through
POST /api/v1/kitchen/orders/{id}/transitions."""

import uuid
from datetime import date, datetime, time
from typing import Annotated, Any, cast
from zoneinfo import ZoneInfo

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.security import create_access_token
from app.db.session import get_session
from app.models.capacity import DailyInventory, ServiceDay, Slot
from app.models.catalogue import MenuItem
from app.models.enums import ItemCategory, OrderStatus, PaymentKind, Role
from app.models.identity import User
from app.models.ordering import Order, Payment
from app.modules.payments.fake import FakePaymentGateway
from app.modules.payments.gateway import PaymentGateway, TransactionGuardedGateway
from app.modules.payments.mockpay_gateway import get_payment_gateway

IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 10, 6)
PLACED_AT = datetime(2026, 10, 6, 9, 0, tzinfo=IST)
# The 12:15 slot ends at 12:30; with P-NOSHOW_GRACE 15 min a no-show is allowed from 12:45.
INSIDE_GRACE = datetime(2026, 10, 6, 12, 40, tzinfo=IST)
AFTER_GRACE = datetime(2026, 10, 6, 12, 45, tzinfo=IST)


class Clock:
    def __init__(self) -> None:
        self.now = PLACED_AT

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def now(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(clock, "now", fake)
    return fake


@pytest.fixture
def api(db_client: TestClient, now: Clock) -> TestClient:
    fake = FakePaymentGateway()

    def guarded(session: Annotated[Session, Depends(get_session)]) -> PaymentGateway:
        return TransactionGuardedGateway(fake, session)

    cast(FastAPI, db_client.app).dependency_overrides[get_payment_gateway] = guarded
    return db_client


def _user(engine: Engine, role: Role) -> User:
    user = User(
        id=uuid.uuid4(),
        name="Asha",
        email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
        password_hash="unused",
        role=role,
    )
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add(user)
    return user


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


@pytest.fixture
def order(api: TestClient, engine: Engine) -> dict[str, Any]:
    """An ACCEPTED order of two Thalis in the 12:15 slot, placed by a Student."""
    item = MenuItem(id=uuid.uuid4(), name="Thali", category=ItemCategory.MEAL, price_paise=8000)
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
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add_all([item, day])
        session.flush()
        session.add_all([slot, DailyInventory(item_id=item.id, service_date=DAY, total=10)])
    student = _user(engine, Role.STUDENT)
    response = api.post(
        "/api/v1/orders",
        json={
            "slot_id": str(slot.id),
            "lines": [{"item_id": str(item.id), "qty": 2}],
            "quoted_payable_paise": 16000,
        },
        headers=_auth(student) | {"Idempotency-Key": uuid.uuid4().hex},
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    assert body["status"] == "ACCEPTED"
    return body | {"student": student}


@pytest.fixture
def cook(engine: Engine) -> User:
    return _user(engine, Role.KITCHEN)


def _act(api: TestClient, user: User, order: dict[str, Any], action: str) -> Response:
    response: Response = api.post(
        f"/api/v1/kitchen/orders/{order['id']}/transitions",
        json={"action": action},
        headers=_auth(user),
    )
    return response


def _held(engine: Engine, order_id: str) -> tuple[OrderStatus, int, int, int]:
    """Status, portions allocated, seats booked and refund records."""
    with Session(engine) as session:
        status = session.get_one(Order, uuid.UUID(order_id)).status
        allocated = session.scalars(select(DailyInventory.allocated)).one()
        booked = session.scalars(select(Slot.booked)).one()
        refunds = session.scalar(
            select(func.count())
            .select_from(Payment)
            .where(Payment.order_id == uuid.UUID(order_id), Payment.kind == PaymentKind.REFUND)
        )
        return status, allocated, booked, refunds or 0


def test_tc_us34_ac1_start_ready_and_picked_up_walk_the_order_to_picked_up(
    api: TestClient, engine: Engine, order: dict[str, Any], cook: User
) -> None:
    seen = []
    for action in ["START", "READY", "PICKED_UP"]:
        response = _act(api, cook, order, action)
        assert response.status_code == 200, response.text
        seen.append(response.json()["status"])

    assert seen == ["PREPARING", "READY", "PICKED_UP"]
    # Picked up: the two portions and the seat were consumed, not returned (T10, FR-21).
    assert _held(engine, order["id"]) == (OrderStatus.PICKED_UP, 2, 1, 0)


def test_tc_us34_ac2_a_no_show_inside_the_grace_period_is_refused(
    api: TestClient, engine: Engine, order: dict[str, Any], cook: User, now: Clock
) -> None:
    assert _act(api, cook, order, "START").status_code == 200
    assert _act(api, cook, order, "READY").status_code == 200
    now.now = INSIDE_GRACE

    response = _act(api, cook, order, "NO_SHOW")

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "message": "too early for a no-show",
        "status": "READY",
        "allowed_from": AFTER_GRACE.isoformat(),
    }
    assert _held(engine, order["id"]) == (OrderStatus.READY, 2, 1, 0)


def test_tc_us34_ac3_a_no_show_after_the_grace_period_keeps_portions_and_refunds_nothing(
    api: TestClient, engine: Engine, order: dict[str, Any], cook: User, now: Clock
) -> None:
    assert _act(api, cook, order, "START").status_code == 200
    assert _act(api, cook, order, "READY").status_code == 200
    now.now = AFTER_GRACE

    response = _act(api, cook, order, "NO_SHOW")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "NO_SHOW"
    # T11: no refund, no portions restored, and the seat is not released either (FR-21).
    assert _held(engine, order["id"]) == (OrderStatus.NO_SHOW, 2, 1, 0)


def test_tc_us34_ac4_an_accepted_order_cannot_be_marked_ready_directly(
    api: TestClient, engine: Engine, order: dict[str, Any], cook: User
) -> None:
    response = _act(api, cook, order, "READY")

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "message": "cannot READY an order that is ACCEPTED",
        "status": "ACCEPTED",
    }
    assert _held(engine, order["id"]) == (OrderStatus.ACCEPTED, 2, 1, 0)


@pytest.mark.parametrize(
    ("before", "action", "status"),
    [
        ([], "PICKED_UP", "ACCEPTED"),
        ([], "NO_SHOW", "ACCEPTED"),
        (["START"], "START", "PREPARING"),
        (["START", "READY", "PICKED_UP"], "READY", "PICKED_UP"),
    ],
)
def test_every_other_move_is_refused_and_changes_nothing(
    api: TestClient,
    engine: Engine,
    order: dict[str, Any],
    cook: User,
    before: list[str],
    action: str,
    status: str,
) -> None:
    """FR-29: any transition not in Table 4.6-A is 409."""
    for step in before:
        assert _act(api, cook, order, step).status_code == 200
    with Session(engine) as session:
        version = session.get_one(Order, uuid.UUID(order["id"])).version

    response = _act(api, cook, order, action)

    assert response.status_code == 409
    assert response.json()["detail"]["status"] == status
    with Session(engine) as session:
        row = session.get_one(Order, uuid.UUID(order["id"]))
        assert (row.status.value, row.version) == (status, version)


def test_the_administrator_may_move_orders_and_a_student_may_not(
    api: TestClient, engine: Engine, order: dict[str, Any]
) -> None:
    admin = _user(engine, Role.ADMIN)

    assert _act(api, order["student"], order, "START").status_code == 403
    assert _act(api, admin, order, "START").status_code == 200


def test_unknown_orders_and_actions_are_refused(
    api: TestClient, order: dict[str, Any], cook: User
) -> None:
    assert _act(api, cook, order | {"id": str(uuid.uuid4())}, "START").status_code == 404
    assert _act(api, cook, order, "COOK").status_code == 422


def test_each_move_is_in_the_order_history_with_the_kitchen_as_actor(
    api: TestClient, order: dict[str, Any], cook: User
) -> None:
    for action in ["START", "READY"]:
        assert _act(api, cook, order, action).status_code == 200

    history = api.get(f"/api/v1/orders/{order['id']}", headers=_auth(order["student"])).json()

    assert [(step["to_status"], step["actor_role"]) for step in history["history"]][-2:] == [
        ("PREPARING", "KITCHEN"),
        ("READY", "KITCHEN"),
    ]


def test_a_student_cancelling_what_they_saw_before_the_start_is_told_the_new_state(
    api: TestClient, engine: Engine, order: dict[str, Any], cook: User, now: Clock
) -> None:
    """UC-13 3c: the kitchen started the order after the Student looked."""
    assert _act(api, cook, order, "START").status_code == 200
    now.now = datetime(2026, 10, 6, 11, 45, tzinfo=IST)

    stale = api.post(
        f"/api/v1/orders/{order['id']}/cancel",
        json={"version": order["version"]},
        headers=_auth(order["student"]) | {"Idempotency-Key": uuid.uuid4().hex},
    )

    assert stale.status_code == 409
    assert stale.json()["detail"]["status"] == "PREPARING"
    # Confirming at the new version gives the late refund: the portions stay cooked.
    confirmed = api.post(
        f"/api/v1/orders/{order['id']}/cancel",
        json={"version": stale.json()["detail"]["version"]},
        headers=_auth(order["student"]) | {"Idempotency-Key": uuid.uuid4().hex},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["refund"]["amount_paise"] == 8000
    assert _held(engine, order["id"]) == (OrderStatus.CANCELLED, 2, 0, 1)
