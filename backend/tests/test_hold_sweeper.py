"""US-24 (CAFIITK-149; FR-34, NFR-14, NFR-15) acceptance tests TC-US24-AC1..AC3, and
the payment outbox that delivers voids and refunds until acknowledged (FR-39).

A crash between reserve and settle is simulated by a gateway whose authorise
raises: the reservation is committed, and no payment result is ever recorded. A
late result is simulated by a gateway that lets the sweeper run before it answers.
"""

import uuid
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from typing import Annotated, Any, cast

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.session import get_session
from app.models.capacity import DailyInventory, ServiceDay, Slot
from app.models.catalogue import MenuItem
from app.models.enums import (
    ItemCategory,
    ModificationStatus,
    OrderStatus,
    PaymentCause,
    PaymentKind,
    PaymentStatus,
    Role,
)
from app.models.identity import User
from app.models.ordering import Order, OrderLine, OrderModification, OrderTransition, Payment
from app.modules.ordering.jobs import ORDERING_JOBS, sweep_expired_holds
from app.modules.ordering.outbox import OutboxDeliverer
from app.modules.ordering.repository import OrderRepository
from app.modules.ordering.sweeper import EXPIRED_REASON, HoldSweeper
from app.modules.payments.fake import FakePaymentGateway
from app.modules.payments.gateway import (
    AuthResult,
    PaymentGateway,
    TransactionGuardedGateway,
)
from app.modules.payments.mockpay_gateway import MockpayGateway, get_payment_gateway

IST = clock.IST
DAY = date(2026, 10, 6)
# After P-MENU_OPEN (08:00) and before the 12:15 slot's cut-off.
NOW = datetime(2026, 10, 6, 9, 0, tzinfo=IST)
THALI, TEA = 8000, 1500
HOLD_EXPIRY_S = get_settings().hold_expiry_s
SWEEP_INTERVAL_S = get_settings().sweep_interval_s


class Crash(Exception):
    """The API process died while waiting for the payment result."""


def _after_expiry() -> datetime:
    """A moment past P-HOLD_EXPIRY for rows created just now (created_at is database time)."""
    return datetime.now(IST) + timedelta(seconds=HOLD_EXPIRY_S + 1)


def _within_expiry() -> datetime:
    return datetime.now(IST) + timedelta(seconds=HOLD_EXPIRY_S - 30)


@pytest.fixture
def menu(engine: Engine) -> dict[str, Any]:
    """Thali (10) and Tea (10); the 12:15 and 13:00 slots of 30 seats."""
    thali = MenuItem(id=uuid.uuid4(), name="Thali", category=ItemCategory.MEAL, price_paise=THALI)
    tea = MenuItem(id=uuid.uuid4(), name="Tea", category=ItemCategory.BEVERAGE, price_paise=TEA)
    early, late = (
        Slot(
            id=uuid.uuid4(),
            service_date=DAY,
            starts_at=datetime(2026, 10, 6, hour, minute, tzinfo=IST),
            ends_at=datetime(2026, 10, 6, hour, minute + 15, tzinfo=IST),
            capacity=30,
        )
        for hour, minute in [(12, 15), (13, 0)]
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
                early,
                late,
                DailyInventory(item_id=thali.id, service_date=DAY, total=10),
                DailyInventory(item_id=tea.id, service_date=DAY, total=10),
            ]
        )
    return {"thali": thali, "tea": tea, "early": early, "late": late}


@pytest.fixture
def api(db_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(clock, "now", lambda: NOW)
    return db_client


def _use_gateway(api: TestClient, gateway: PaymentGateway) -> None:
    def guarded(session: Annotated[Session, Depends(get_session)]) -> PaymentGateway:
        # The guard proves no payment call is made with a transaction open (NFR-6).
        return TransactionGuardedGateway(gateway, session)

    cast(FastAPI, api.app).dependency_overrides[get_payment_gateway] = guarded


class CrashOnAuthorise(FakePaymentGateway):
    """Approves the first `approve` authorisations, then dies before answering."""

    def __init__(self, approve: int = 0) -> None:
        super().__init__()
        self.approve = approve

    def authorise(self, reference: str, amount_paise: int) -> AuthResult:
        if len(self.authorised) >= self.approve:
            self.authorised.append((reference, amount_paise))
            raise Crash
        return super().authorise(reference, amount_paise)


class LateResult(FakePaymentGateway):
    """Approves the first `approve` authorisations; the next answers only after `meanwhile`."""

    def __init__(self, meanwhile: Callable[[], object], approve: int = 0) -> None:
        super().__init__()
        self.meanwhile = meanwhile
        self.approve = approve

    def authorise(self, reference: str, amount_paise: int) -> AuthResult:
        if len(self.authorised) == self.approve:
            self.meanwhile()
        return super().authorise(reference, amount_paise)


def _student(engine: Engine) -> User:
    user = User(
        id=uuid.uuid4(),
        name="Asha",
        email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
        password_hash="unused",
        role=Role.STUDENT,
    )
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add(user)
    return user


def _headers(user: User) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_access_token(user.id, user.role)}",
        "Idempotency-Key": uuid.uuid4().hex,
    }


def _cart(menu: dict[str, Any], slot: str = "early", **qty: int) -> dict[str, Any]:
    return {
        "slot_id": str(menu[slot].id),
        "lines": [{"item_id": str(menu[name].id), "qty": q} for name, q in qty.items()],
    }


def _place(api: TestClient, student: User, menu: dict[str, Any]) -> httpx.Response:
    """A Thali and a Tea in the 12:15 slot."""
    response: httpx.Response = api.post(
        "/api/v1/orders",
        json=_cart(menu, thali=1, tea=1) | {"quoted_payable_paise": THALI + TEA},
        headers=_headers(student),
    )
    return response


def _modify(
    api: TestClient, student: User, order: dict[str, Any], cart: dict[str, Any], payable: int
) -> httpx.Response:
    response: httpx.Response = api.patch(
        f"/api/v1/orders/{order['id']}",
        json=cart | {"quoted_payable_paise": payable, "version": order["version"]},
        headers=_headers(student),
    )
    return response


def _crashed_order(api: TestClient, engine: Engine, menu: dict[str, Any]) -> uuid.UUID:
    """An order committed as PENDING_PAYMENT whose payment result never arrived."""
    _use_gateway(api, CrashOnAuthorise())
    # The client sees a generic 500 (NFR-23); the order stays committed as a hold.
    assert _place(api, _student(engine), menu).status_code == 500
    with Session(engine) as session:
        order = session.scalars(
            select(Order).where(Order.status == OrderStatus.PENDING_PAYMENT)
        ).one()
        return order.id


def _sweep(engine: Engine, now: datetime) -> tuple[int, int]:
    with Session(engine, expire_on_commit=False) as session:
        result = HoldSweeper(session, HOLD_EXPIRY_S).sweep(now)
        return result.orders_expired, result.modifications_released


def _deliver(engine: Engine, gateway: PaymentGateway) -> int:
    with Session(engine, expire_on_commit=False) as session:
        return OutboxDeliverer(session, TransactionGuardedGateway(gateway, session)).deliver()


def _holds(engine: Engine, menu: dict[str, Any]) -> dict[str, int]:
    with Session(engine) as session:
        allocated = {row.item_id: row.allocated for row in session.scalars(select(DailyInventory))}
        booked = {row.id: row.booked for row in session.scalars(select(Slot))}
    return {
        "thali": allocated[menu["thali"].id],
        "tea": allocated[menu["tea"].id],
        "early": booked[menu["early"].id],
        "late": booked[menu["late"].id],
    }


def _order(engine: Engine, order_id: uuid.UUID) -> Order:
    with Session(engine, expire_on_commit=False) as session:
        return session.get_one(Order, order_id)


def _payments(engine: Engine, order_id: uuid.UUID, kind: PaymentKind) -> list[Payment]:
    with Session(engine, expire_on_commit=False) as session:
        return list(
            session.scalars(
                select(Payment)
                .where(Payment.order_id == order_id, Payment.kind == kind)
                .order_by(Payment.created_at, Payment.id)
            )
        )


NO_HOLDS = {"thali": 0, "tea": 0, "early": 0, "late": 0}
ONE_ORDER = {"thali": 1, "tea": 1, "early": 1, "late": 0}


def test_tc_us24_ac1_a_crashed_order_expires_within_hold_expiry_plus_sweep_interval(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    order_id = _crashed_order(api, engine, menu)
    assert _holds(engine, menu) == ONE_ORDER

    # Not before P-HOLD_EXPIRY ...
    assert _sweep(engine, _within_expiry()) == (0, 0)
    assert _order(engine, order_id).status is OrderStatus.PENDING_PAYMENT
    # ... and by the first sweep after it, at most P-SWEEP_INTERVAL later (NFR-14).
    assert _sweep(engine, _after_expiry()) == (1, 0)

    assert _order(engine, order_id).status is OrderStatus.PAYMENT_FAILED
    assert _holds(engine, menu) == NO_HOLDS
    with Session(engine) as session:
        transition = session.scalars(
            select(OrderTransition).where(
                OrderTransition.order_id == order_id,
                OrderTransition.to_status == OrderStatus.PAYMENT_FAILED,
            )
        ).one()
    assert (transition.reason, transition.actor_id) == (EXPIRED_REASON, None)
    # The authorisation may still land, so its void waits in the outbox.
    [auth] = _payments(engine, order_id, PaymentKind.AUTH)
    [void] = _payments(engine, order_id, PaymentKind.VOID)
    assert auth.status is PaymentStatus.FAILED
    assert (void.cause, void.status, void.modification_id) == (
        PaymentCause.EXPIRY,
        PaymentStatus.PENDING,
        None,
    )

    # A second sweep finds nothing more to do.
    assert _sweep(engine, _after_expiry()) == (0, 0)
    assert len(_payments(engine, order_id, PaymentKind.VOID)) == 1


def test_tc_us24_ac1_the_worker_recovers_holds_at_start_up(
    api: TestClient,
    engine: Engine,
    menu: dict[str, Any],
    configured_database: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NFR-15: the sweeper runs once at start-up, before its first interval."""
    order_id = _crashed_order(api, engine, menu)
    [job] = [job for job in ORDERING_JOBS if job.name == "hold-sweeper"]
    assert job.run_at_startup
    assert job.every_s == SWEEP_INTERVAL_S

    monkeypatch.setattr(clock, "now", _after_expiry)
    sweep_expired_holds()

    assert _order(engine, order_id).status is OrderStatus.PAYMENT_FAILED
    assert _holds(engine, menu) == NO_HOLDS


def test_tc_us24_ac2_a_late_approval_leaves_the_order_failed_and_is_voided(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    gateway = LateResult(lambda: _sweep(engine, _after_expiry()))
    _use_gateway(api, gateway)

    response = _place(api, _student(engine), menu)

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "PAYMENT_FAILED"
    order_id = uuid.UUID(response.json()["id"])
    assert _holds(engine, menu) == NO_HOLDS
    # Exactly one void, the sweeper's, however many parties saw the late result.
    [void] = _payments(engine, order_id, PaymentKind.VOID)
    assert void.cause is PaymentCause.EXPIRY

    assert _deliver(engine, gateway) == 1

    [auth] = _payments(engine, order_id, PaymentKind.AUTH)
    assert gateway.voided == [str(auth.id)]
    assert _payments(engine, order_id, PaymentKind.VOID)[0].status is PaymentStatus.SUCCEEDED
    assert _order(engine, order_id).status is OrderStatus.PAYMENT_FAILED


def test_tc_us24_ac2_against_real_mockpay_the_late_approval_is_refused(
    api: TestClient, engine: Engine, menu: dict[str, Any], mockpay_url: str
) -> None:
    """mockpay records the void first, so the authorisation that arrives after it fails."""
    with httpx.Client(base_url=mockpay_url, timeout=2) as http:
        mockpay = MockpayGateway(http)

        def expire_and_void() -> None:
            _sweep(engine, _after_expiry())
            assert _deliver(engine, mockpay) == 1

        class Late:
            def authorise(self, reference: str, amount_paise: int) -> AuthResult:
                expire_and_void()
                return mockpay.authorise(reference, amount_paise)

            def void(self, reference: str) -> None:
                mockpay.void(reference)

            def refund(self, reference: str, auth_reference: str, amount_paise: int) -> None:
                mockpay.refund(reference, auth_reference, amount_paise)

        _use_gateway(api, Late())
        response = _place(api, _student(engine), menu)

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "PAYMENT_FAILED"
    order_id = uuid.UUID(response.json()["id"])
    [auth] = _payments(engine, order_id, PaymentKind.AUTH)
    # mockpay answered the late authorise as not approved: nothing was charged.
    assert auth.status is PaymentStatus.FAILED
    assert _order(engine, order_id).paid_paise == 0
    assert _holds(engine, menu) == NO_HOLDS


def test_tc_us24_ac3_accepted_and_later_orders_are_untouched(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    gateway = FakePaymentGateway()
    _use_gateway(api, gateway)
    placed = [_place(api, _student(engine), menu).json() for _ in range(3)]
    ids = [uuid.UUID(order["id"]) for order in placed]
    with Session(engine) as session, session.begin():
        for order_id, status in zip(
            ids[1:], [OrderStatus.PREPARING, OrderStatus.READY], strict=True
        ):
            session.execute(update(Order).where(Order.id == order_id).values(status=status))
    before = [
        (o.status, o.version, o.paid_paise, o.slot_id)
        for o in map(lambda i: _order(engine, i), ids)
    ]
    holds = _holds(engine, menu)

    assert _sweep(engine, _after_expiry()) == (0, 0)

    after = [
        (o.status, o.version, o.paid_paise, o.slot_id)
        for o in map(lambda i: _order(engine, i), ids)
    ]
    assert after == before
    assert _holds(engine, menu) == holds
    for order_id in ids:
        assert _payments(engine, order_id, PaymentKind.VOID) == []


def test_a_fresh_pending_order_is_not_expired(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    order_id = _crashed_order(api, engine, menu)
    assert _sweep(engine, datetime.now(IST)) == (0, 0)
    assert _order(engine, order_id).status is OrderStatus.PENDING_PAYMENT
    assert _holds(engine, menu) == ONE_ORDER


def _crashed_modification(
    api: TestClient, engine: Engine, menu: dict[str, Any], cart: dict[str, Any], payable: int
) -> dict[str, Any]:
    """An ACCEPTED order whose price-raising modification never got its payment result."""
    _use_gateway(api, CrashOnAuthorise(approve=1))
    student = _student(engine)
    order = _place(api, student, menu)
    assert order.json()["status"] == "ACCEPTED"
    assert _modify(api, student, order.json(), cart, payable).status_code == 500
    return dict(order.json(), student=student)


def _lines(engine: Engine, order_id: uuid.UUID) -> dict[uuid.UUID, int]:
    with Session(engine) as session:
        return {
            line.item_id: line.qty
            for line in session.scalars(select(OrderLine).where(OrderLine.order_id == order_id))
        }


def test_an_expired_modification_releases_its_holds_and_leaves_the_order_as_before(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    """FR-34b: two Thalis and a move to 13:00, never paid for."""
    order = _crashed_modification(
        api, engine, menu, _cart(menu, "late", thali=2, tea=1), 2 * THALI + TEA
    )
    order_id = uuid.UUID(order["id"])
    lines_before = _lines(engine, order_id)
    # The hold took the extra Thali and a seat at 13:00 on top of the order's own.
    assert _holds(engine, menu) == {"thali": 2, "tea": 1, "early": 1, "late": 1}

    assert _sweep(engine, _within_expiry()) == (0, 0)
    assert _sweep(engine, _after_expiry()) == (0, 1)

    assert _holds(engine, menu) == ONE_ORDER
    after = _order(engine, order_id)
    assert (after.status, after.slot_id, after.paid_paise) == (
        OrderStatus.ACCEPTED,
        menu["early"].id,
        THALI + TEA,
    )
    assert _lines(engine, order_id) == lines_before
    with Session(engine) as session:
        modification = session.scalars(
            select(OrderModification).where(OrderModification.order_id == order_id)
        ).one()
    assert modification.status is ModificationStatus.RELEASED
    [_, auth] = _payments(engine, order_id, PaymentKind.AUTH)
    [void] = _payments(engine, order_id, PaymentKind.VOID)
    assert auth.status is PaymentStatus.FAILED
    assert (void.cause, void.modification_id, void.amount_paise) == (
        PaymentCause.EXPIRY,
        modification.id,
        THALI,
    )


def test_a_late_approval_of_an_expired_modification_is_never_refunded_against(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    """The voided authorisation is not a charge: a later cancel refunds only the real one."""
    gateway = LateResult(lambda: _sweep(engine, _after_expiry()), approve=1)
    _use_gateway(api, gateway)
    student = _student(engine)
    order = _place(api, student, menu).json()

    response = _modify(api, student, order, _cart(menu, thali=2, tea=1), 2 * THALI + TEA)

    assert response.status_code == 409, response.text
    order_id = uuid.UUID(order["id"])
    assert _holds(engine, menu) == ONE_ORDER
    placement_auth, modify_auth = _payments(engine, order_id, PaymentKind.AUTH)
    # mockpay approved it late, so it is SUCCEEDED; the sweeper's void cancels it.
    assert modify_auth.status is PaymentStatus.SUCCEEDED
    [void] = _payments(engine, order_id, PaymentKind.VOID)
    assert void.cause is PaymentCause.EXPIRY
    with Session(engine) as session:
        assert OrderRepository(session).get_charges(order_id) == [(placement_auth.id, THALI + TEA)]

    current = api.get(f"/api/v1/orders/{order_id}", headers=_headers(student)).json()
    cancelled = api.post(
        f"/api/v1/orders/{order_id}/cancel",
        json={"version": current["version"]},
        headers=_headers(student),
    )
    assert cancelled.status_code == 200, cancelled.text
    [refund] = _payments(engine, order_id, PaymentKind.REFUND)
    assert gateway.refunded == [(str(refund.id), str(placement_auth.id), THALI + TEA)]


def test_the_outbox_retries_a_void_until_the_gateway_acknowledges_it(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    order_id = _crashed_order(api, engine, menu)
    _sweep(engine, _after_expiry())
    gateway = FakePaymentGateway(unavailable=True)

    assert _deliver(engine, gateway) == 0
    [void] = _payments(engine, order_id, PaymentKind.VOID)
    assert (void.status, void.attempts) == (PaymentStatus.PENDING, 1)

    gateway.unavailable = False
    assert _deliver(engine, gateway) == 1
    assert _deliver(engine, gateway) == 0  # nothing left to send

    [void] = _payments(engine, order_id, PaymentKind.VOID)
    [auth] = _payments(engine, order_id, PaymentKind.AUTH)
    assert (void.status, void.attempts) == (PaymentStatus.SUCCEEDED, 2)
    assert gateway.voided == [str(auth.id)]


def test_the_outbox_delivers_a_refund_the_gateway_did_not_acknowledge(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    """FR-39: a cancel while mockpay is down leaves the refund PENDING; the outbox sends it."""
    gateway = FakePaymentGateway()
    _use_gateway(api, gateway)
    student = _student(engine)
    order = _place(api, student, menu).json()
    gateway.unavailable = True
    cancelled = api.post(
        f"/api/v1/orders/{order['id']}/cancel",
        json={"version": order["version"]},
        headers=_headers(student),
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["refund"]["status"] == "PENDING"
    order_id = uuid.UUID(order["id"])

    gateway.unavailable = False
    assert _deliver(engine, gateway) == 1

    [refund] = _payments(engine, order_id, PaymentKind.REFUND)
    [auth] = _payments(engine, order_id, PaymentKind.AUTH)
    assert refund.status is PaymentStatus.SUCCEEDED
    assert gateway.refunded == [(str(refund.id), str(auth.id), THALI + TEA)]


def test_the_worker_runs_the_sweeper_and_the_outbox() -> None:
    names = {job.name for job in ORDERING_JOBS}
    assert {"hold-sweeper", "payment-outbox"} <= names
