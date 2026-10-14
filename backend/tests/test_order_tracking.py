"""US-29 (FR-40) acceptance tests TC-US29-AC1..AC2 through GET /api/v1/orders/{id},
and US-05 (FR-7) TC-US05-AC1..AC2: a Student's orders are private.

The kitchen's transitions (CAFIITK-159) are not built yet, so `_kitchen_moves`
applies them the way the state machine allows, writing the same rows the kitchen
endpoint will. Replace it with calls to that endpoint once it exists.
"""

import uuid
from datetime import date, datetime, time
from typing import Annotated, Any, cast
from zoneinfo import ZoneInfo

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.security import create_access_token
from app.db.session import get_session
from app.models.capacity import DailyInventory, ServiceDay, Slot
from app.models.catalogue import MenuItem
from app.models.enums import ItemCategory, OrderStatus, Role
from app.models.identity import User
from app.models.ordering import Order, OrderLine, OrderTransition
from app.models.platform import AuditLog
from app.modules.ordering.state_machine import transition
from app.modules.payments.fake import FakePaymentGateway
from app.modules.payments.gateway import AuthOutcome, PaymentGateway, TransactionGuardedGateway
from app.modules.payments.mockpay_gateway import get_payment_gateway

ORDERS = "/api/v1/orders"
IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 10, 6)
NOW = datetime(2026, 10, 6, 9, 0, tzinfo=IST)
THALI = 8000


def _add(engine: Engine, *rows: Any) -> None:
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add_all(rows)


def _user(engine: Engine, role: Role = Role.STUDENT) -> User:
    user = User(
        id=uuid.uuid4(),
        name="Asha",
        email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
        password_hash="unused",
        role=role,
    )
    _add(engine, user)
    return user


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


@pytest.fixture
def gateway() -> FakePaymentGateway:
    return FakePaymentGateway()


@pytest.fixture
def api(
    db_client: TestClient, gateway: FakePaymentGateway, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    def guarded(session: Annotated[Session, Depends(get_session)]) -> PaymentGateway:
        return TransactionGuardedGateway(gateway, session)

    cast(FastAPI, db_client.app).dependency_overrides[get_payment_gateway] = guarded
    monkeypatch.setattr(clock, "now", lambda: NOW)
    return db_client


@pytest.fixture
def menu(engine: Engine) -> dict[str, Any]:
    thali = MenuItem(id=uuid.uuid4(), name="Thali", category=ItemCategory.MEAL, price_paise=THALI)
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
    _add(engine, thali, day)
    _add(engine, slot, DailyInventory(item_id=thali.id, service_date=DAY, total=10))
    return {"thali": thali, "slot": slot}


def _place(api: TestClient, menu: dict[str, Any], student: User) -> dict[str, Any]:
    body = {
        "slot_id": str(menu["slot"].id),
        "lines": [{"item_id": str(menu["thali"].id), "qty": 1}],
        "quoted_payable_paise": THALI,
    }
    headers = _auth(student) | {"Idempotency-Key": uuid.uuid4().hex}
    response = api.post(ORDERS, json=body, headers=headers)
    assert response.status_code == 201, response.text
    order: dict[str, Any] = response.json()
    return order


def _kitchen_moves(engine: Engine, order_id: str, *statuses: OrderStatus) -> None:
    """Stand-in for the kitchen endpoint: one legal transition per transaction."""
    for to_status in statuses:
        with Session(engine) as session, session.begin():
            order = session.get(Order, uuid.UUID(order_id), with_for_update=True)
            assert order is not None
            transition(order.status, to_status)
            session.add(
                OrderTransition(
                    order_id=order.id,
                    from_status=order.status,
                    to_status=to_status,
                    actor_role=Role.KITCHEN,
                )
            )
            order.status = to_status
            order.version += 1


def _track(api: TestClient, order_id: str, user: User) -> Any:
    return api.get(f"{ORDERS}/{order_id}", headers=_auth(user))


def _security_events(engine: Engine, order_id: str) -> list[AuditLog]:
    with Session(engine) as session:
        rows = session.scalars(
            select(AuditLog).where(AuditLog.action == "ORDER_ACCESS_DENIED").order_by(AuditLog.id)
        ).all()
    return [row for row in rows if (row.after or {}).get("order_id") == order_id]


def test_tc_us29_ac1_the_status_the_kitchen_sets_is_what_the_student_sees(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    student = _user(engine)
    order = _place(api, menu, student)
    assert _track(api, order["id"], student).json()["status"] == "ACCEPTED"

    _kitchen_moves(engine, order["id"], OrderStatus.PREPARING, OrderStatus.READY)

    tracked = _track(api, order["id"], student)
    assert tracked.status_code == 200
    assert tracked.json()["status"] == "READY"
    assert tracked.json()["version"] == order["version"] + 2


def test_tc_us29_ac2_a_completed_order_lists_every_transition_with_its_time(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    student = _user(engine)
    order = _place(api, menu, student)
    _kitchen_moves(
        engine, order["id"], OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.PICKED_UP
    )

    body = _track(api, order["id"], student).json()

    steps = [(step["from_status"], step["to_status"]) for step in body["history"]]
    assert steps == [
        (None, "PENDING_PAYMENT"),
        ("PENDING_PAYMENT", "ACCEPTED"),
        ("ACCEPTED", "PREPARING"),
        ("PREPARING", "READY"),
        ("READY", "PICKED_UP"),
    ]
    times = [datetime.fromisoformat(step["at"]) for step in body["history"]]
    assert all(at.tzinfo is not None for at in times)
    assert times == sorted(times)
    assert [step["actor_role"] for step in body["history"]] == [
        "STUDENT",
        None,
        "KITCHEN",
        "KITCHEN",
        "KITCHEN",
    ]
    assert body["status"] == "PICKED_UP"


def test_the_order_comes_with_its_price_and_slot(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    student = _user(engine)
    order = _place(api, menu, student)

    body = _track(api, order["id"], student).json()

    assert body["id"] == order["id"]
    assert body["slot_id"] == str(menu["slot"].id)
    assert body["paid_paise"] == THALI
    assert body["price"] == order["price"]
    assert body["created_at"] == order["created_at"]


def test_a_declined_payment_shows_why_in_the_history(
    api: TestClient, engine: Engine, menu: dict[str, Any], gateway: FakePaymentGateway
) -> None:
    gateway.outcome = AuthOutcome.DECLINED
    student = _user(engine)
    order = _place(api, menu, student)

    body = _track(api, order["id"], student).json()

    assert body["status"] == "PAYMENT_FAILED"
    assert body["history"][-1]["to_status"] == "PAYMENT_FAILED"
    assert body["history"][-1]["reason"] == "declined"


def test_tc_us05_ac1_another_students_order_is_404_and_logged(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    owner, other = _user(engine), _user(engine)
    order = _place(api, menu, owner)

    response = _track(api, order["id"], other)

    assert response.status_code == 404
    assert response.json() == {"detail": "Order not found"}
    [event] = _security_events(engine, order["id"])
    assert event.actor_id == str(other.id)
    assert event.actor_role == "STUDENT"
    assert event.entity_type == "security"


def _state(engine: Engine, order_id: str) -> tuple[Any, ...]:
    """Everything a modify or cancel would change."""
    with Session(engine) as session:
        order = session.get(Order, uuid.UUID(order_id))
        assert order is not None
        lines = session.scalars(
            select(OrderLine.item_id, OrderLine.qty).where(OrderLine.order_id == order.id)
        ).all()
        stock = session.scalars(select(DailyInventory.allocated)).all()
        booked = session.scalars(select(Slot.booked)).all()
        return order.status, order.version, order.slot_id, sorted(lines), stock, booked


def test_tc_us05_ac2_another_student_cannot_modify_or_cancel(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    owner, other = _user(engine), _user(engine)
    order = _place(api, menu, owner)
    before = _state(engine, order["id"])
    headers = _auth(other) | {"Idempotency-Key": uuid.uuid4().hex}

    modify = api.patch(
        f"{ORDERS}/{order['id']}",
        json={
            "slot_id": str(menu["slot"].id),
            "lines": [{"item_id": str(menu["thali"].id), "qty": 2}],
            "version": order["version"],
            "quoted_payable_paise": 2 * THALI,
        },
        headers=headers,
    )
    cancel = api.post(
        f"{ORDERS}/{order['id']}/cancel",
        json={"version": order["version"]},
        headers=_auth(other) | {"Idempotency-Key": uuid.uuid4().hex},
    )

    # Answered as if the order did not exist, and nothing about it changed.
    assert (modify.status_code, modify.json()) == (404, {"detail": "Order not found"})
    assert (cancel.status_code, cancel.json()) == (404, {"detail": "Order not found"})
    assert _state(engine, order["id"]) == before
    events = _security_events(engine, order["id"])
    assert [(event.actor_id, (event.after or {}).get("operation")) for event in events] == [
        (str(other.id), "modify"),
        (str(other.id), "cancel"),
    ]


def test_an_order_that_does_not_exist_is_404_the_same_way(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    missing = str(uuid.uuid4())

    response = _track(api, missing, _user(engine))

    # Indistinguishable from someone else's order (FR-7), but nothing to log.
    assert response.status_code == 404
    assert response.json() == {"detail": "Order not found"}
    assert _security_events(engine, missing) == []


@pytest.mark.parametrize("role", [Role.KITCHEN, Role.ADMIN])
def test_staff_cannot_use_the_student_tracking_endpoint(
    api: TestClient, engine: Engine, menu: dict[str, Any], role: Role
) -> None:
    order = _place(api, menu, _user(engine))

    assert _track(api, order["id"], _user(engine, role)).status_code == 403


def test_tracking_needs_a_token(api: TestClient, engine: Engine, menu: dict[str, Any]) -> None:
    order = _place(api, menu, _user(engine))

    assert api.get(f"{ORDERS}/{order['id']}").status_code == 401


def test_a_malformed_order_id_is_422(api: TestClient, engine: Engine) -> None:
    assert _track(api, "not-a-uuid", _user(engine)).status_code == 422
