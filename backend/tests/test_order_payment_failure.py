"""US-23 (CAFIITK-148; FR-33, NFR-14) acceptance tests TC-US23-AC1..AC2.

Orders are placed through POST /api/v1/orders against real PostgreSQL, and the
payment goes over HTTP to a running mockpay, so the timeout is a real one.
TC-US23-AC3 (the outcome control is unavailable in production) is in test_mockpay.py.
"""

import time as stopwatch
import uuid
from collections.abc import Iterator
from datetime import date, datetime, time
from typing import Annotated, Any, cast

import httpx
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
from app.models.enums import ItemCategory, OrderStatus, PaymentKind, PaymentStatus, Role
from app.models.identity import User
from app.models.ordering import OrderTransition, Payment
from app.modules.payments.gateway import PaymentGateway, TransactionGuardedGateway
from app.modules.payments.mockpay_gateway import MockpayGateway, get_payment_gateway

URL = "/api/v1/orders"
DAY = date(2026, 10, 6)
# After P-MENU_OPEN (08:00) and before the 12:15 slot stops taking bookings (12:00).
NOW = datetime(2026, 10, 6, 9, 0, tzinfo=clock.IST)
# P-PAY_TIMEOUT for these tests; mockpay's timeout mode holds a request for 1 s.
PAY_TIMEOUT_S = 0.5
# NFR-14: holds are released within P-PAY_TIMEOUT + 5 s of a decline or timeout.
RELEASE_DEADLINE_S = PAY_TIMEOUT_S + 5
PRICE = 8000


@pytest.fixture
def mockpay(mockpay_url: str) -> Iterator[httpx.Client]:
    """The mockpay outcome control; the outcome is reset to approve afterwards."""
    with httpx.Client(base_url=mockpay_url) as client:
        yield client
        client.put("/_control/outcome", json={"mode": "approve"})


@pytest.fixture
def api(
    db_client: TestClient, mockpay_url: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """The API with its real mockpay adapter, behind the NFR-6 guard."""
    monkeypatch.setattr(clock, "now", lambda: NOW)
    with httpx.Client(base_url=mockpay_url, timeout=PAY_TIMEOUT_S) as http:

        def gateway(session: Annotated[Session, Depends(get_session)]) -> PaymentGateway:
            return TransactionGuardedGateway(MockpayGateway(http), session)

        cast(FastAPI, db_client.app).dependency_overrides[get_payment_gateway] = gateway
        yield db_client


@pytest.fixture
def last_thali(engine: Engine) -> dict[str, Any]:
    """One portion of Thali and one seat in the 12:15 slot: a held one blocks everyone else."""
    thali = MenuItem(id=uuid.uuid4(), name="Thali", category=ItemCategory.MEAL, price_paise=PRICE)
    slot = Slot(
        id=uuid.uuid4(),
        service_date=DAY,
        starts_at=datetime(2026, 10, 6, 12, 15, tzinfo=clock.IST),
        ends_at=datetime(2026, 10, 6, 12, 30, tzinfo=clock.IST),
        capacity=1,
    )
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add(thali)
        session.add(
            ServiceDay(
                service_date=DAY,
                window_start=time(12, 0),
                window_end=time(14, 30),
                slot_len_min=15,
                default_capacity=1,
            )
        )
        session.flush()
        session.add_all([slot, DailyInventory(item_id=thali.id, service_date=DAY, total=1)])
    return {
        "slot_id": str(slot.id),
        "lines": [{"item_id": str(thali.id), "qty": 1}],
        "quoted_payable_paise": PRICE,
    }


def _student(engine: Engine) -> dict[str, str]:
    user = User(
        id=uuid.uuid4(),
        name="Asha",
        email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
        password_hash="unused",
        role=Role.STUDENT,
    )
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add(user)
    return {
        "Authorization": f"Bearer {create_access_token(user.id, user.role)}",
        "Idempotency-Key": uuid.uuid4().hex,
    }


def _place(api: TestClient, engine: Engine, cart: dict[str, Any]) -> tuple[dict[str, Any], float]:
    """Place an order as a new student; returns the order and how long the request took."""
    started = stopwatch.monotonic()
    response = api.post(URL, json=cart, headers=_student(engine))
    elapsed = stopwatch.monotonic() - started
    assert response.status_code == 201, response.text
    order: dict[str, Any] = response.json()
    return order, elapsed


def _holds(engine: Engine) -> tuple[int, int]:
    """(portions allocated, seats booked)."""
    with Session(engine) as session:
        return (
            session.scalars(select(DailyInventory.allocated)).one(),
            session.scalars(select(Slot.booked)).one(),
        )


def _payments(engine: Engine, order_id: str) -> dict[PaymentKind, PaymentStatus]:
    with Session(engine) as session:
        rows = session.scalars(select(Payment).where(Payment.order_id == uuid.UUID(order_id)))
        return {payment.kind: payment.status for payment in rows}


def _failure_reason(engine: Engine, order_id: str) -> str | None:
    with Session(engine) as session:
        return session.scalars(
            select(OrderTransition.reason).where(
                OrderTransition.order_id == uuid.UUID(order_id),
                OrderTransition.to_status == OrderStatus.PAYMENT_FAILED,
            )
        ).one()


def _assert_released_for_others(api: TestClient, engine: Engine, cart: dict[str, Any]) -> None:
    """The portion and the seat are back on the menu and slot list, and can be bought."""
    reader = _student(engine)
    [thali] = api.get("/api/v1/menu", params={"date": DAY.isoformat()}, headers=reader).json()[
        "items"
    ]
    [slot] = api.get("/api/v1/slots", params={"date": DAY.isoformat()}, headers=reader).json()[
        "slots"
    ]
    assert (thali["available_portions"], thali["orderable"]) == (1, True)
    assert (slot["remaining_seats"], slot["bookable"]) == (1, True)

    order, _ = _place(api, engine, cart)
    assert order["status"] == "ACCEPTED"
    assert _holds(engine) == (1, 1)


def test_tc_us23_ac1_declined_payment_releases_the_portions_and_seat(
    api: TestClient, engine: Engine, mockpay: httpx.Client, last_thali: dict[str, Any]
) -> None:
    mockpay.put("/_control/outcome", json={"mode": "decline"})

    order, elapsed = _place(api, engine, last_thali)

    assert order["status"] == "PAYMENT_FAILED"
    assert order["paid_paise"] == 0
    assert _holds(engine) == (0, 0)
    assert elapsed < RELEASE_DEADLINE_S
    assert _failure_reason(engine, order["id"]) == "declined"
    # A decline is definite: there is nothing to void.
    assert _payments(engine, order["id"]) == {PaymentKind.AUTH: PaymentStatus.FAILED}

    mockpay.put("/_control/outcome", json={"mode": "approve"})
    _assert_released_for_others(api, engine, last_thali)


def test_tc_us23_ac2_timed_out_payment_releases_the_portions_and_seat(
    api: TestClient, engine: Engine, mockpay: httpx.Client, last_thali: dict[str, Any]
) -> None:
    mockpay.put("/_control/outcome", json={"mode": "timeout"})

    order, elapsed = _place(api, engine, last_thali)

    assert order["status"] == "PAYMENT_FAILED"
    assert order["paid_paise"] == 0
    assert _holds(engine) == (0, 0)
    # The gateway waited the full P-PAY_TIMEOUT, and the release met the NFR-14 deadline.
    assert PAY_TIMEOUT_S <= elapsed < RELEASE_DEADLINE_S
    assert _failure_reason(engine, order["id"]) == "timeout"
    # The authorisation may have landed, so a void waits in the outbox (SADD 6.2).
    assert _payments(engine, order["id"]) == {
        PaymentKind.AUTH: PaymentStatus.FAILED,
        PaymentKind.VOID: PaymentStatus.PENDING,
    }

    mockpay.put("/_control/outcome", json={"mode": "approve"})
    _assert_released_for_others(api, engine, last_thali)


def test_approval_that_arrives_after_the_timeout_does_not_accept_the_order(
    api: TestClient, engine: Engine, mockpay: httpx.Client, last_thali: dict[str, Any]
) -> None:
    mockpay.put("/_control/outcome", json={"mode": "approve", "delay_ms": 800})

    order, elapsed = _place(api, engine, last_thali)

    assert order["status"] == "PAYMENT_FAILED"
    assert _holds(engine) == (0, 0)
    assert elapsed < RELEASE_DEADLINE_S
    assert _payments(engine, order["id"])[PaymentKind.VOID] is PaymentStatus.PENDING


def test_approved_payment_over_http_accepts_the_order_and_keeps_the_holds(
    api: TestClient, engine: Engine, mockpay: httpx.Client, last_thali: dict[str, Any]
) -> None:
    order, _ = _place(api, engine, last_thali)

    assert order["status"] == "ACCEPTED"
    assert order["paid_paise"] == PRICE
    assert _holds(engine) == (1, 1)
    with Session(engine) as session:
        payment = session.scalars(select(Payment)).one()
    assert payment.status is PaymentStatus.SUCCEEDED
    assert payment.provider_ref is not None and payment.provider_ref.startswith("mp_")
