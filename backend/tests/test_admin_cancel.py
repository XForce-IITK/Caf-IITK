"""US-36 (CAFIITK-161; FR-38, FR-39) acceptance tests TC-US36-AC1..AC2 through
POST /api/v1/admin/orders/{id}/cancel, plus the paths around them.

Orders are placed through the API with the in-memory gateway; the kitchen's
transitions are applied directly to the row, as test_order_cancel.py does.
"""

import uuid
from datetime import date, datetime, time
from typing import Annotated, Any, cast

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from app.core import clock
from app.core.security import create_access_token
from app.db.session import get_session
from app.models.capacity import DailyInventory, ServiceDay, Slot
from app.models.catalogue import MenuItem
from app.models.enums import (
    ItemCategory,
    OrderStatus,
    PaymentCause,
    PaymentKind,
    PaymentStatus,
    Role,
)
from app.models.identity import User
from app.models.ordering import Order, OrderTransition, Payment
from app.modules.payments.fake import FakePaymentGateway
from app.modules.payments.gateway import PaymentGateway, TransactionGuardedGateway
from app.modules.payments.mockpay_gateway import get_payment_gateway

IST = clock.IST
DAY = date(2026, 10, 6)
# After P-MENU_OPEN and before the 12:15 slot's cut-off, so the Student can order.
NOW = datetime(2026, 10, 6, 9, 0, tzinfo=IST)
# Well past the Student's cut-off: the Administrator has none.
AT_THE_COUNTER = datetime(2026, 10, 6, 12, 20, tzinfo=IST)
THALI, TEA = 8000, 1500
REASON = "Wrong item packed; refunded at the counter"


@pytest.fixture
def menu(engine: Engine) -> dict[str, Any]:
    """Thali (10) and Tea (10); the 12:15 slot of 30 seats."""
    thali = MenuItem(id=uuid.uuid4(), name="Thali", category=ItemCategory.MEAL, price_paise=THALI)
    tea = MenuItem(id=uuid.uuid4(), name="Tea", category=ItemCategory.BEVERAGE, price_paise=TEA)
    slot = Slot(
        id=uuid.uuid4(),
        service_date=DAY,
        starts_at=datetime(2026, 10, 6, 12, 15, tzinfo=IST),
        ends_at=datetime(2026, 10, 6, 12, 30, tzinfo=IST),
        capacity=30,
    )
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add_all(
            [
                thali,
                tea,
                ServiceDay(
                    service_date=DAY,
                    window_start=time(12, 0),
                    window_end=time(14, 30),
                    slot_len_min=15,
                    default_capacity=30,
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                slot,
                DailyInventory(item_id=thali.id, service_date=DAY, total=10),
                DailyInventory(item_id=tea.id, service_date=DAY, total=10),
            ]
        )
    return {"thali": thali, "tea": tea, "slot": slot}


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def now(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(clock, "now", fake)
    return fake


@pytest.fixture
def gateway(db_client: TestClient) -> FakePaymentGateway:
    fake = FakePaymentGateway()

    def guarded(session: Annotated[Session, Depends(get_session)]) -> PaymentGateway:
        # The guard proves no payment call is made with a transaction open (NFR-6).
        return TransactionGuardedGateway(fake, session)

    cast(FastAPI, db_client.app).dependency_overrides[get_payment_gateway] = guarded
    return fake


@pytest.fixture
def api(db_client: TestClient, gateway: FakePaymentGateway, now: Clock) -> TestClient:
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


@pytest.fixture
def admin(engine: Engine) -> User:
    return _user(engine, Role.ADMIN)


def _headers(user: User, key: str | None = None) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_access_token(user.id, user.role)}",
        "Idempotency-Key": key or uuid.uuid4().hex,
    }


def _place(api: TestClient, engine: Engine, menu: dict[str, Any]) -> dict[str, Any]:
    """A Thali and a Tea in the 12:15 slot, paid in full."""
    response = api.post(
        "/api/v1/orders",
        json={
            "slot_id": str(menu["slot"].id),
            "lines": [
                {"item_id": str(menu["thali"].id), "qty": 1},
                {"item_id": str(menu["tea"].id), "qty": 1},
            ],
            "quoted_payable_paise": THALI + TEA,
        },
        headers=_headers(_user(engine, Role.STUDENT)),
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    assert body["status"] == "ACCEPTED"
    return body


def _set_status(engine: Engine, order: dict[str, Any], status: OrderStatus) -> dict[str, Any]:
    """Move the order on as the kitchen would, bumping its version (NFR-5)."""
    with Session(engine) as session, session.begin():
        session.execute(
            update(Order)
            .where(Order.id == uuid.UUID(order["id"]))
            .values(status=status, version=Order.version + 1)
        )
    return order | {"status": status.value, "version": order["version"] + 1}


def _cancel(
    api: TestClient,
    user: User,
    order: dict[str, Any],
    *,
    reason: str | None = REASON,
    version: int | None = None,
    key: str | None = None,
) -> httpx.Response:
    body: dict[str, Any] = {"version": version or order["version"]}
    if reason is not None:
        body["reason"] = reason
    response: httpx.Response = api.post(
        f"/api/v1/admin/orders/{order['id']}/cancel", json=body, headers=_headers(user, key)
    )
    return response


def _holds(engine: Engine, menu: dict[str, Any]) -> tuple[int, int, int]:
    """(Thali portions allocated, Tea portions allocated, seats booked)."""
    with Session(engine) as session:
        allocated = {row.item_id: row.allocated for row in session.scalars(select(DailyInventory))}
        booked = session.get_one(Slot, menu["slot"].id).booked
    return allocated[menu["thali"].id], allocated[menu["tea"].id], booked


def _refunds(engine: Engine, order: dict[str, Any]) -> list[Payment]:
    with Session(engine, expire_on_commit=False) as session:
        return list(
            session.scalars(
                select(Payment).where(
                    Payment.order_id == uuid.UUID(order["id"]),
                    Payment.kind == PaymentKind.REFUND,
                )
            )
        )


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_tc_us36_ac1_cancelling_without_a_reason_is_unprocessable(
    api: TestClient,
    engine: Engine,
    menu: dict[str, Any],
    admin: User,
    gateway: FakePaymentGateway,
    reason: str | None,
) -> None:
    order = _place(api, engine, menu)

    response = _cancel(api, admin, order, reason=reason)

    assert response.status_code == 422, response.text
    with Session(engine) as session:
        assert session.get_one(Order, uuid.UUID(order["id"])).status is OrderStatus.ACCEPTED
    assert _holds(engine, menu) == (1, 1, 1)
    assert _refunds(engine, order) == []
    assert gateway.refunded == []


def test_tc_us36_ac2_a_ready_order_is_cancelled_with_a_full_refund_and_only_the_seat_back(
    api: TestClient,
    engine: Engine,
    menu: dict[str, Any],
    admin: User,
    gateway: FakePaymentGateway,
    now: Clock,
) -> None:
    order = _set_status(engine, _place(api, engine, menu), OrderStatus.READY)
    now.now = AT_THE_COUNTER

    response = _cancel(api, admin, order)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "CANCELLED"
    assert body["refund"] == {"amount_paise": THALI + TEA, "status": "SUCCEEDED"}
    # The seat is released; the food was already made, so the portions are not (T9).
    assert _holds(engine, menu) == (1, 1, 0)
    [refund] = _refunds(engine, order)
    assert (refund.cause, refund.amount_paise) == (PaymentCause.CANCEL, THALI + TEA)
    assert [(reference, amount) for reference, _, amount in gateway.refunded] == [
        (str(refund.id), THALI + TEA)
    ]
    with Session(engine) as session:
        transition = session.scalars(
            select(OrderTransition).where(
                OrderTransition.order_id == uuid.UUID(order["id"]),
                OrderTransition.to_status == OrderStatus.CANCELLED,
            )
        ).one()
    assert (transition.from_status, transition.actor_id, transition.actor_role) == (
        OrderStatus.READY,
        admin.id,
        Role.ADMIN,
    )
    assert transition.reason == REASON


def test_an_accepted_order_returns_its_portions_and_seat(
    api: TestClient, engine: Engine, menu: dict[str, Any], admin: User, now: Clock
) -> None:
    order = _place(api, engine, menu)
    now.now = AT_THE_COUNTER  # after the Student's cut-off

    response = _cancel(api, admin, order)

    assert response.status_code == 200, response.text
    assert response.json()["refund"]["amount_paise"] == THALI + TEA
    assert _holds(engine, menu) == (0, 0, 0)


def test_a_preparing_order_gets_a_full_refund_not_the_late_percentage(
    api: TestClient, engine: Engine, menu: dict[str, Any], admin: User
) -> None:
    order = _set_status(engine, _place(api, engine, menu), OrderStatus.PREPARING)

    response = _cancel(api, admin, order)

    assert response.status_code == 200, response.text
    assert response.json()["refund"]["amount_paise"] == THALI + TEA
    assert _holds(engine, menu) == (1, 1, 0)  # T7


@pytest.mark.parametrize("role", [Role.STUDENT, Role.KITCHEN])
def test_only_the_administrator_may_cancel_any_order(
    api: TestClient, engine: Engine, menu: dict[str, Any], role: Role
) -> None:
    order = _place(api, engine, menu)

    response = _cancel(api, _user(engine, role), order)

    assert response.status_code == 403
    assert _holds(engine, menu) == (1, 1, 1)


@pytest.mark.parametrize(
    "status", [OrderStatus.PICKED_UP, OrderStatus.NO_SHOW, OrderStatus.CANCELLED]
)
def test_a_finished_order_cannot_be_cancelled(
    api: TestClient, engine: Engine, menu: dict[str, Any], admin: User, status: OrderStatus
) -> None:
    order = _set_status(engine, _place(api, engine, menu), status)

    response = _cancel(api, admin, order)

    assert response.status_code == 409
    assert response.json()["detail"]["status"] == status.value
    assert _refunds(engine, order) == []


def test_a_stale_version_is_refused_with_the_current_state(
    api: TestClient, engine: Engine, menu: dict[str, Any], admin: User
) -> None:
    seen = _place(api, engine, menu)
    _set_status(engine, seen, OrderStatus.PREPARING)

    response = _cancel(api, admin, seen)

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "message": "the order has changed",
        "status": "PREPARING",
        "version": seen["version"] + 1,
        "refund_paise": THALI + TEA,
    }
    assert _holds(engine, menu) == (1, 1, 1)


def test_a_repeated_request_returns_the_same_result_and_refunds_once(
    api: TestClient,
    engine: Engine,
    menu: dict[str, Any],
    admin: User,
    gateway: FakePaymentGateway,
) -> None:
    order = _place(api, engine, menu)
    key = uuid.uuid4().hex

    first = _cancel(api, admin, order, key=key)
    again = _cancel(api, admin, order, key=key)

    assert (first.status_code, again.status_code) == (200, 200)
    assert again.json() == first.json()
    assert len(_refunds(engine, order)) == 1
    assert len(gateway.refunded) == 1


def test_the_same_key_with_a_different_reason_is_unprocessable(
    api: TestClient, engine: Engine, menu: dict[str, Any], admin: User
) -> None:
    order = _place(api, engine, menu)
    key = uuid.uuid4().hex
    assert _cancel(api, admin, order, key=key).status_code == 200

    response = _cancel(api, admin, order, key=key, reason="Another reason")

    assert response.status_code == 422


def test_an_unknown_order_is_not_found(api: TestClient, admin: User) -> None:
    order = {"id": str(uuid.uuid4()), "version": 1}
    assert _cancel(api, admin, order).status_code == 404


def test_a_refund_mockpay_does_not_acknowledge_stays_pending_for_the_outbox(
    api: TestClient,
    engine: Engine,
    menu: dict[str, Any],
    admin: User,
    gateway: FakePaymentGateway,
) -> None:
    order = _place(api, engine, menu)
    gateway.unavailable = True

    response = _cancel(api, admin, order)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CANCELLED"
    assert response.json()["refund"] == {"amount_paise": THALI + TEA, "status": "PENDING"}
    [refund] = _refunds(engine, order)
    assert (refund.status, refund.attempts) == (PaymentStatus.PENDING, 1)
