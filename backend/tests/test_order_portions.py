"""US-13 (FR-16) acceptance tests TC-US13-AC1..AC4: portions follow the order lifecycle.

AC3 and AC4 cancel an order, which arrives in Sprint 2; they are skipped here so
the gap stays visible in every test report. The rule they test is already fixed
in the state machine (see test_order_state_machine.py).
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
from app.models.ordering import Order
from app.modules.payments.fake import FakePaymentGateway
from app.modules.payments.gateway import (
    AuthOutcome,
    AuthResult,
    PaymentGateway,
    TransactionGuardedGateway,
)
from app.modules.payments.mockpay_gateway import get_payment_gateway

IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 10, 6)
NOW = datetime(2026, 10, 6, 9, 0, tzinfo=IST)
TWO_THALIS = 16000


@pytest.fixture
def thali(engine: Engine) -> dict[str, Any]:
    """Thali with 10 portions available, and a bookable slot."""
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
    student = User(
        id=uuid.uuid4(),
        name="Asha",
        email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
        password_hash="unused",
        role=Role.STUDENT,
    )
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add_all([item, day, student])
        session.flush()
        session.add_all([slot, DailyInventory(item_id=item.id, service_date=DAY, total=10)])
    token = create_access_token(student.id, student.role)
    return {"item": item, "slot": slot, "auth": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def api(db_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(clock, "now", lambda: NOW)
    return db_client


def _use_gateway(client: TestClient, gateway: PaymentGateway) -> None:
    def guarded(session: Annotated[Session, Depends(get_session)]) -> PaymentGateway:
        return TransactionGuardedGateway(gateway, session)

    cast(FastAPI, client.app).dependency_overrides[get_payment_gateway] = guarded


def _order_two(api: TestClient, thali: dict[str, Any]) -> dict[str, Any]:
    response = api.post(
        "/api/v1/orders",
        json={
            "slot_id": str(thali["slot"].id),
            "lines": [{"item_id": str(thali["item"].id), "qty": 2}],
            "quoted_payable_paise": TWO_THALIS,
        },
        headers=thali["auth"] | {"Idempotency-Key": uuid.uuid4().hex},
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _available_on_menu(api: TestClient, thali: dict[str, Any]) -> int:
    """What a Student sees: GET /menu for the service date."""
    response = api.get("/api/v1/menu", params={"date": DAY.isoformat()}, headers=thali["auth"])
    assert response.status_code == 200, response.text
    [item] = response.json()["items"]
    available: int = item["available_portions"]
    return available


def _available_in_db(engine: Engine) -> int:
    with Session(engine) as session:
        stock = session.scalars(select(DailyInventory)).one()
        return stock.total - stock.allocated


def test_tc_us13_ac1_portions_are_reserved_while_the_order_awaits_payment(
    api: TestClient, engine: Engine, thali: dict[str, Any]
) -> None:
    seen: dict[str, Any] = {}

    class LooksWhileAuthorising:
        """The gateway call is the moment the order is in PENDING_PAYMENT."""

        def authorise(self, reference: str, amount_paise: int) -> AuthResult:
            with Session(engine) as session:
                seen["status"] = session.scalars(select(Order.status)).one()
            seen["available"] = _available_in_db(engine)
            return AuthResult(AuthOutcome.APPROVED, provider_ref="ok")

        def void(self, reference: str) -> None: ...

        def refund(self, reference: str, auth_reference: str, amount_paise: int) -> None: ...

    _use_gateway(api, LooksWhileAuthorising())
    assert _available_on_menu(api, thali) == 10

    order = _order_two(api, thali)

    assert seen == {"status": OrderStatus.PENDING_PAYMENT, "available": 8}
    # Accepting the order keeps the reservation.
    assert order["status"] == "ACCEPTED"
    assert _available_on_menu(api, thali) == 8


def test_tc_us13_ac2_declined_payment_returns_the_portions(
    api: TestClient, engine: Engine, thali: dict[str, Any]
) -> None:
    _use_gateway(api, FakePaymentGateway(outcome=AuthOutcome.DECLINED))

    order = _order_two(api, thali)

    assert order["status"] == "PAYMENT_FAILED"
    # No further action: the 10 are back as soon as the response arrives.
    assert _available_on_menu(api, thali) == 10
    assert _available_in_db(engine) == 10


@pytest.mark.skip(reason="needs the cancel endpoint, US-28 (Sprint 2)")
def test_tc_us13_ac3_cancelling_an_accepted_order_restores_the_portions() -> None:
    """T6: ACCEPTED -> CANCELLED releases the portions."""


@pytest.mark.skip(
    reason="needs the cancel endpoint, US-28, and the kitchen start, US-34 (Sprint 2)"
)
def test_tc_us13_ac4_cancelling_a_preparing_order_does_not_restore_the_portions() -> None:
    """T7: PREPARING -> CANCELLED releases the seat but not the portions."""
