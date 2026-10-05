"""US-22 (FR-29, FR-30, FR-33) acceptance tests TC-US22-AC1..AC3 through POST /api/v1/orders."""

import uuid
from collections.abc import Callable
from datetime import date, datetime, time
from typing import Annotated, Any, cast
from zoneinfo import ZoneInfo

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
    ItemStatus,
    OrderStatus,
    PaymentKind,
    PaymentStatus,
    Role,
)
from app.models.identity import User
from app.models.ordering import Order, OrderLine, OrderTransition, Payment, PriceSnapshot
from app.models.platform import AuditLog
from app.modules.ordering.retry import TransientFailureError
from app.modules.ordering.service import OrderService
from app.modules.payments.fake import FakePaymentGateway
from app.modules.payments.gateway import (
    AuthOutcome,
    AuthResult,
    PaymentGateway,
    TransactionGuardedGateway,
)
from app.modules.payments.mockpay_gateway import get_payment_gateway

URL = "/api/v1/orders"
IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 10, 6)
# After P-MENU_OPEN (08:00) and before the 12:15 slot stops taking bookings (12:00).
NOW = datetime(2026, 10, 6, 9, 0, tzinfo=IST)
# Thali Rs 80 + 2 x Tea Rs 15, no discount rules, no subsidy.
PAYABLE = 11000


def _add(engine: Engine, *rows: Any) -> None:
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add_all(rows)


def _user(engine: Engine, role: Role = Role.STUDENT, *, eligible: bool = False) -> User:
    user = User(
        id=uuid.uuid4(),
        name="Asha",
        email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
        password_hash="unused",
        role=role,
        subsidy_eligible=eligible,
    )
    _add(engine, user)
    return user


def _headers(user: User, key: str | None = None) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_access_token(user.id, user.role)}",
        "Idempotency-Key": key or uuid.uuid4().hex,
    }


@pytest.fixture
def menu(engine: Engine) -> dict[str, Any]:
    thali = MenuItem(id=uuid.uuid4(), name="Thali", category=ItemCategory.MEAL, price_paise=8000)
    tea = MenuItem(id=uuid.uuid4(), name="Tea", category=ItemCategory.BEVERAGE, price_paise=1500)
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
    _add(engine, thali, tea, day)
    _add(
        engine,
        slot,
        DailyInventory(item_id=thali.id, service_date=DAY, total=10),
        DailyInventory(item_id=tea.id, service_date=DAY, total=10),
    )
    return {"thali": thali, "tea": tea, "slot": slot}


@pytest.fixture
def gateway() -> FakePaymentGateway:
    return FakePaymentGateway()


def _use_gateway(client: TestClient, gateway: PaymentGateway) -> None:
    """Install `gateway` behind the NFR-6 guard, as the real dependency does."""

    def guarded(session: Annotated[Session, Depends(get_session)]) -> PaymentGateway:
        return TransactionGuardedGateway(gateway, session)

    cast(FastAPI, client.app).dependency_overrides[get_payment_gateway] = guarded


@pytest.fixture
def set_clock(monkeypatch: pytest.MonkeyPatch) -> Callable[[datetime], None]:
    def set_to(now: datetime) -> None:
        monkeypatch.setattr(clock, "now", lambda: now)

    set_to(NOW)
    return set_to


@pytest.fixture
def api(
    db_client: TestClient, gateway: FakePaymentGateway, set_clock: Callable[[datetime], None]
) -> TestClient:
    _use_gateway(db_client, gateway)
    return db_client


def _cart(menu: dict[str, Any], quoted: int = PAYABLE) -> dict[str, Any]:
    return {
        "slot_id": str(menu["slot"].id),
        "lines": [
            {"item_id": str(menu["thali"].id), "qty": 1},
            {"item_id": str(menu["tea"].id), "qty": 2},
        ],
        "quoted_payable_paise": quoted,
    }


def _allocated(engine: Engine, item: MenuItem) -> int:
    with Session(engine) as session:
        return session.scalars(
            select(DailyInventory.allocated).where(DailyInventory.item_id == item.id)
        ).one()


def _booked(engine: Engine, slot: Slot) -> int:
    with Session(engine) as session:
        return session.scalars(select(Slot.booked).where(Slot.id == slot.id)).one()


def _holds(engine: Engine, menu: dict[str, Any]) -> tuple[int, int, int]:
    return (
        _allocated(engine, menu["thali"]),
        _allocated(engine, menu["tea"]),
        _booked(engine, menu["slot"]),
    )


def _orders(engine: Engine) -> list[Order]:
    with Session(engine) as session:
        return list(session.scalars(select(Order)))


def _audit(engine: Engine, order_id: str) -> list[AuditLog]:
    """This order's audit entries in order; audit_log is not emptied between tests."""
    with Session(engine) as session:
        rows = session.scalars(select(AuditLog).order_by(AuditLog.id)).all()
    return [
        row
        for row in rows
        if row.entity_id == order_id or (row.after or {}).get("order_id") == order_id
    ]


def _set(engine: Engine, model: Any, where: Any, **values: Any) -> None:
    with Session(engine) as session, session.begin():
        session.execute(update(model).where(where).values(**values))


def test_tc_us22_ac1_approved_order_is_accepted_with_holds_snapshot_and_audit(
    api: TestClient, engine: Engine, menu: dict[str, Any], gateway: FakePaymentGateway
) -> None:
    student = _user(engine)

    response = api.post(URL, json=_cart(menu), headers=_headers(student))

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "ACCEPTED"
    assert body["paid_paise"] == PAYABLE
    assert body["price"]["payable_paise"] == PAYABLE
    order_id = uuid.UUID(body["id"])

    # Exactly the ordered portions and one seat, even with three units in the cart.
    assert _holds(engine, menu) == (1, 2, 1)

    with Session(engine) as session:
        lines = {
            line.item_id: line.qty
            for line in session.scalars(select(OrderLine).where(OrderLine.order_id == order_id))
        }
        snapshots = session.scalars(
            select(PriceSnapshot).where(PriceSnapshot.order_id == order_id)
        ).all()
        transitions = session.execute(
            select(OrderTransition.from_status, OrderTransition.to_status)
            .where(OrderTransition.order_id == order_id)
            .order_by(OrderTransition.id)
        ).all()
        payment = session.scalars(select(Payment).where(Payment.order_id == order_id)).one()
    audit = _audit(engine, body["id"])
    seat_audit = audit[3]

    assert lines == {menu["thali"].id: 1, menu["tea"].id: 2}
    assert [(s.version, s.payable_paise) for s in snapshots] == [(1, PAYABLE)]
    assert [line["qty"] for line in snapshots[0].breakdown["lines"]] == [1, 2]
    assert [tuple(row) for row in transitions] == [
        (None, OrderStatus.PENDING_PAYMENT),
        (OrderStatus.PENDING_PAYMENT, OrderStatus.ACCEPTED),
    ]
    assert (payment.kind, payment.status) == (PaymentKind.AUTH, PaymentStatus.SUCCEEDED)
    assert payment.provider_ref == f"fake_{payment.id}"
    assert gateway.authorised == [(str(payment.id), PAYABLE)]
    assert [row.action for row in audit] == [
        "ORDER_TRANSITION",
        "PORTIONS_ALLOCATED",
        "PORTIONS_ALLOCATED",
        "SEAT_ALLOCATED",
        "ORDER_TRANSITION",
    ]
    assert (seat_audit.before, seat_audit.actor_id) == ({"booked": 0}, str(student.id))
    assert seat_audit.after == {"booked": 1, "order_id": str(order_id)}


def test_tc_us22_ac2_sold_out_item_is_named_and_nothing_is_reserved(
    api: TestClient, engine: Engine, menu: dict[str, Any], gateway: FakePaymentGateway
) -> None:
    # Tea has just sold out.
    _set(engine, DailyInventory, DailyInventory.item_id == menu["tea"].id, allocated=10)

    response = api.post(URL, json=_cart(menu), headers=_headers(_user(engine)))

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["item_ids"] == [str(menu["tea"].id)]
    assert response.json()["detail"]["slot_id"] is None
    assert _holds(engine, menu) == (0, 10, 0)
    assert _orders(engine) == []
    assert gateway.authorised == []


def test_tc_us22_ac3_before_menu_open_is_409_and_nothing_is_reserved(
    api: TestClient,
    engine: Engine,
    menu: dict[str, Any],
    gateway: FakePaymentGateway,
    set_clock: Callable[[datetime], None],
) -> None:
    set_clock(datetime(2026, 10, 6, 7, 59, tzinfo=IST))

    response = api.post(URL, json=_cart(menu), headers=_headers(_user(engine)))

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["opens_at"] == "2026-10-06T08:00:00+05:30"
    assert _holds(engine, menu) == (0, 0, 0)
    assert _orders(engine) == []
    assert gateway.authorised == []


def test_order_is_accepted_from_the_moment_the_menu_opens(
    api: TestClient, engine: Engine, menu: dict[str, Any], set_clock: Callable[[datetime], None]
) -> None:
    set_clock(datetime(2026, 10, 6, 8, 0, tzinfo=IST))
    response = api.post(URL, json=_cart(menu), headers=_headers(_user(engine)))
    assert response.status_code == 201, response.text


@pytest.mark.parametrize(
    ("outcome", "voids"), [(AuthOutcome.DECLINED, 0), (AuthOutcome.TIMEOUT, 1)]
)
def test_failed_payment_ends_payment_failed_and_returns_the_holds(
    api: TestClient,
    engine: Engine,
    menu: dict[str, Any],
    gateway: FakePaymentGateway,
    outcome: AuthOutcome,
    voids: int,
) -> None:
    gateway.outcome = outcome

    response = api.post(URL, json=_cart(menu), headers=_headers(_user(engine)))

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "PAYMENT_FAILED"
    assert response.json()["paid_paise"] == 0
    assert _holds(engine, menu) == (0, 0, 0)
    with Session(engine) as session:
        payments = {p.kind: p.status for p in session.scalars(select(Payment))}
        reason = session.scalars(
            select(OrderTransition.reason).where(
                OrderTransition.to_status == OrderStatus.PAYMENT_FAILED
            )
        ).one()
    released = [
        row.actor_role
        for row in _audit(engine, response.json()["id"])
        if row.action == "PORTIONS_RELEASED"
    ]
    assert payments[PaymentKind.AUTH] is PaymentStatus.FAILED
    # A timed-out authorisation may have landed, so a void is queued for the outbox.
    assert (PaymentKind.VOID in payments) == bool(voids)
    assert reason == outcome.value.lower()
    assert released == ["SYSTEM", "SYSTEM"]


def test_late_approval_after_the_hold_expired_changes_nothing_and_is_voided(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    class ExpiresWhileAuthorising:
        """Stands in for the sweeper expiring the order during the gateway call (FR-34)."""

        def authorise(self, reference: str, amount_paise: int) -> AuthResult:
            _set(
                engine,
                Order,
                Order.status == OrderStatus.PENDING_PAYMENT,
                status=OrderStatus.PAYMENT_FAILED,
            )
            return AuthResult(AuthOutcome.APPROVED, provider_ref="late")

        def void(self, reference: str) -> None: ...

        def refund(self, reference: str, auth_reference: str, amount_paise: int) -> None: ...

    _use_gateway(api, ExpiresWhileAuthorising())

    response = api.post(URL, json=_cart(menu), headers=_headers(_user(engine)))

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "PAYMENT_FAILED"
    assert response.json()["paid_paise"] == 0
    # The stand-in did not release the holds, and neither may the late result.
    assert _holds(engine, menu) == (1, 2, 1)
    with Session(engine) as session:
        kinds = sorted(p.kind.value for p in session.scalars(select(Payment)))
    assert kinds == ["AUTH", "VOID"]


def test_full_slot_is_named_in_a_409(api: TestClient, engine: Engine, menu: dict[str, Any]) -> None:
    _set(engine, Slot, Slot.id == menu["slot"].id, booked=30)

    response = api.post(URL, json=_cart(menu), headers=_headers(_user(engine)))

    assert response.status_code == 409
    assert response.json()["detail"]["slot_id"] == str(menu["slot"].id)
    assert response.json()["detail"]["item_ids"] == []
    assert _holds(engine, menu) == (0, 0, 30)


def test_slot_inside_book_close_is_not_bookable(
    api: TestClient, engine: Engine, menu: dict[str, Any], set_clock: Callable[[datetime], None]
) -> None:
    # P-BOOK_CLOSE is 15 min, so the 12:15 slot closes at 12:00 sharp.
    set_clock(datetime(2026, 10, 6, 12, 0, tzinfo=IST))

    response = api.post(URL, json=_cart(menu), headers=_headers(_user(engine)))

    assert response.status_code == 409
    assert response.json()["detail"]["slot_id"] == str(menu["slot"].id)
    assert _holds(engine, menu) == (0, 0, 0)


def test_every_unavailable_item_and_the_slot_are_named_together(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    _set(engine, MenuItem, MenuItem.id == menu["thali"].id, unavailable=True)
    _set(engine, MenuItem, MenuItem.id == menu["tea"].id, status=ItemStatus.REMOVED)
    _set(engine, Slot, Slot.id == menu["slot"].id, booked=30)

    response = api.post(URL, json=_cart(menu), headers=_headers(_user(engine)))

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["item_ids"] == [str(menu["thali"].id), str(menu["tea"].id)]
    assert detail["slot_id"] == str(menu["slot"].id)


def test_item_with_an_expired_unavailable_flag_is_orderable(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    _set(
        engine,
        MenuItem,
        MenuItem.id == menu["thali"].id,
        unavailable=True,
        unavailable_until=datetime(2026, 10, 6, 8, 30, tzinfo=IST),
    )
    response = api.post(URL, json=_cart(menu), headers=_headers(_user(engine)))
    assert response.status_code == 201, response.text


def test_item_with_no_inventory_row_or_too_few_portions_is_unavailable(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    soup = MenuItem(id=uuid.uuid4(), name="Soup", category=ItemCategory.SNACK, price_paise=3000)
    _add(engine, soup)
    # One Tea left, two wanted.
    _set(engine, DailyInventory, DailyInventory.item_id == menu["tea"].id, allocated=9)
    body = _cart(menu)
    body["lines"].append({"item_id": str(soup.id), "qty": 1})

    response = api.post(URL, json=body, headers=_headers(_user(engine)))

    assert response.status_code == 409
    assert response.json()["detail"]["item_ids"] == [str(menu["tea"].id), str(soup.id)]
    assert _holds(engine, menu) == (0, 9, 0)


def test_price_differing_from_the_quote_is_409_with_a_fresh_quote(
    api: TestClient, engine: Engine, menu: dict[str, Any], gateway: FakePaymentGateway
) -> None:
    response = api.post(URL, json=_cart(menu, quoted=10000), headers=_headers(_user(engine)))

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["quote"]["payable_paise"] == PAYABLE
    assert _holds(engine, menu) == (0, 0, 0)
    assert _orders(engine) == []
    assert gateway.authorised == []


def test_repeat_with_the_same_key_returns_the_same_order_once(
    api: TestClient, engine: Engine, menu: dict[str, Any], gateway: FakePaymentGateway
) -> None:
    headers = _headers(_user(engine))

    first = api.post(URL, json=_cart(menu), headers=headers)
    second = api.post(URL, json=_cart(menu), headers=headers)

    assert (first.status_code, second.status_code) == (201, 201)
    assert second.json() == first.json()
    assert _holds(engine, menu) == (1, 2, 1)
    assert len(_orders(engine)) == 1
    assert len(gateway.authorised) == 1


def test_same_key_with_a_different_cart_is_422(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    headers = _headers(_user(engine))
    assert api.post(URL, json=_cart(menu), headers=headers).status_code == 201
    other = _cart(menu)
    other["lines"].pop()
    other["quoted_payable_paise"] = 8000

    response = api.post(URL, json=other, headers=headers)

    assert response.status_code == 422
    assert _holds(engine, menu) == (1, 2, 1)


def test_rejected_request_does_not_use_up_its_key(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    headers = _headers(_user(engine))
    tea = DailyInventory.item_id == menu["tea"].id
    _set(engine, DailyInventory, tea, allocated=10)
    assert api.post(URL, json=_cart(menu), headers=headers).status_code == 409

    _set(engine, DailyInventory, tea, allocated=0)
    response = api.post(URL, json=_cart(menu), headers=headers)

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "ACCEPTED"


def test_subsidy_is_applied_once_per_student_per_day(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    student = _user(engine, eligible=True)

    # Rs 110 less the Rs 20 subsidy.
    first = api.post(URL, json=_cart(menu, quoted=9000), headers=_headers(student))
    second = api.post(URL, json=_cart(menu, quoted=9000), headers=_headers(student))

    assert first.status_code == 201, first.text
    assert first.json()["subsidy_applied"] is True
    assert second.status_code == 409
    assert second.json()["detail"]["quote"]["subsidy_paise"] == 0
    assert second.json()["detail"]["quote"]["payable_paise"] == PAYABLE


def test_unknown_item_is_422(api: TestClient, engine: Engine, menu: dict[str, Any]) -> None:
    ghost = uuid.uuid4()
    body = _cart(menu)
    body["lines"].append({"item_id": str(ghost), "qty": 1})

    response = api.post(URL, json=body, headers=_headers(_user(engine)))

    assert response.status_code == 422
    assert response.json()["detail"]["item_ids"] == [str(ghost)]
    assert _holds(engine, menu) == (0, 0, 0)


def test_quantity_above_max_qty_is_422(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    body = _cart(menu)
    body["lines"][0]["qty"] = 4  # P-MAX_QTY defaults to 3
    response = api.post(URL, json=body, headers=_headers(_user(engine)))
    assert response.status_code == 422
    assert "may not exceed 3" in response.text


def test_unknown_slot_is_404(api: TestClient, engine: Engine, menu: dict[str, Any]) -> None:
    body = _cart(menu) | {"slot_id": str(uuid.uuid4())}
    assert api.post(URL, json=body, headers=_headers(_user(engine))).status_code == 404


def test_idempotency_key_is_required(api: TestClient, engine: Engine, menu: dict[str, Any]) -> None:
    headers = _headers(_user(engine))
    del headers["Idempotency-Key"]
    assert api.post(URL, json=_cart(menu), headers=headers).status_code == 422


@pytest.mark.parametrize("role", [Role.KITCHEN, Role.ADMIN])
def test_only_students_can_place_orders(
    api: TestClient, engine: Engine, menu: dict[str, Any], role: Role
) -> None:
    response = api.post(URL, json=_cart(menu), headers=_headers(_user(engine, role)))
    assert response.status_code == 403


def test_placing_an_order_requires_a_token(api: TestClient, menu: dict[str, Any]) -> None:
    response = api.post(URL, json=_cart(menu), headers={"Idempotency-Key": "k"})
    assert response.status_code == 401


def test_persistent_transient_failure_is_503_with_retry_after(
    api: TestClient, engine: Engine, menu: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def always_busy(*args: Any, **kwargs: Any) -> None:
        raise TransientFailureError

    monkeypatch.setattr(OrderService, "place", always_busy)

    response = api.post(URL, json=_cart(menu), headers=_headers(_user(engine)))

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
