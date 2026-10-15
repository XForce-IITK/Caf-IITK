"""US-28 (FR-21, FR-37, FR-39) acceptance tests TC-US28-AC1..AC5 through
POST /api/v1/orders/{id}/cancel, plus US-04 AC2 (Kitchen Staff cannot cancel).

The kitchen "start" endpoint (US-34) is not merged yet, so PREPARING and READY
orders are set up here through the order state machine, as the kitchen will do.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
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
from app.models.enums import ItemCategory, OrderStatus, PaymentKind, PaymentStatus, Role
from app.models.identity import User
from app.models.ordering import Order, OrderTransition, Payment
from app.models.platform import AuditLog
from app.modules.ordering.service import cancel_refund_paise
from app.modules.ordering.state_machine import transition
from app.modules.payments.fake import FakePaymentGateway
from app.modules.payments.gateway import PaymentGateway, TransactionGuardedGateway
from app.modules.payments.mockpay_gateway import get_payment_gateway

IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 10, 6)
PLACED_AT = datetime(2026, 10, 6, 9, 0, tzinfo=IST)
# The 12:15 slot's cut-off is 12:05 (P-CUTOFF 10 min).
THIRTY_MIN_BEFORE = datetime(2026, 10, 6, 11, 45, tzinfo=IST)
INSIDE_CUTOFF = datetime(2026, 10, 6, 12, 10, tzinfo=IST)
TWO_THALIS = 16000


def _student(engine: Engine, role: Role = Role.STUDENT) -> User:
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


def _headers(user: User, key: str | None = None) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_access_token(user.id, user.role)}",
        "Idempotency-Key": key or uuid.uuid4().hex,
    }


@pytest.fixture
def thali(engine: Engine) -> dict[str, Any]:
    """Thali with 10 portions and a 30-seat 12:15 slot."""
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
    return {"item": item, "slot": slot}


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
def gateway(db_client: TestClient) -> FakePaymentGateway:
    fake = FakePaymentGateway()

    def guarded(session: Annotated[Session, Depends(get_session)]) -> PaymentGateway:
        # The guard proves the refund is never sent with a transaction open (NFR-6).
        return TransactionGuardedGateway(fake, session)

    cast(FastAPI, db_client.app).dependency_overrides[get_payment_gateway] = guarded
    return fake


@pytest.fixture
def api(db_client: TestClient, gateway: FakePaymentGateway, now: Clock) -> TestClient:
    return db_client


def _place(api: TestClient, student: User, thali: dict[str, Any]) -> dict[str, Any]:
    response = api.post(
        "/api/v1/orders",
        json={
            "slot_id": str(thali["slot"].id),
            "lines": [{"item_id": str(thali["item"].id), "qty": 2}],
            "quoted_payable_paise": TWO_THALIS,
        },
        headers=_headers(student),
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    assert body["status"] == "ACCEPTED"
    return body


def _advance(engine: Engine, order_id: str, *statuses: OrderStatus) -> int:
    """Move the order as the kitchen would (T5, T8) and return its new version."""
    with Session(engine) as session, session.begin():
        order = session.get_one(Order, uuid.UUID(order_id), with_for_update=True)
        for to_status in statuses:
            transition(order.status, to_status)
            session.add(
                OrderTransition(order_id=order.id, from_status=order.status, to_status=to_status)
            )
            order.status = to_status
            order.version += 1
        return order.version


def _cancel(
    api: TestClient,
    student: User,
    order: dict[str, Any],
    *,
    version: int | None = None,
    key: str | None = None,
) -> Response:
    response: Response = api.post(
        f"/api/v1/orders/{order['id']}/cancel",
        json={"version": version or order["version"]},
        headers=_headers(student, key),
    )
    return response


def _state(engine: Engine, order_id: str) -> tuple[OrderStatus, int, int, int]:
    """Status, version, portions available and seats booked."""
    with Session(engine) as session:
        order = session.get_one(Order, uuid.UUID(order_id))
        stock = session.scalars(select(DailyInventory)).one()
        slot = session.scalars(select(Slot)).one()
        return order.status, order.version, stock.total - stock.allocated, slot.booked


def _refunds(engine: Engine, order_id: str) -> list[Payment]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(Payment).where(
                    Payment.order_id == uuid.UUID(order_id), Payment.kind == PaymentKind.REFUND
                )
            )
        )


def test_tc_us28_ac1_cancelling_an_accepted_order_refunds_all_and_restores_everything(
    api: TestClient,
    engine: Engine,
    thali: dict[str, Any],
    gateway: FakePaymentGateway,
    now: Clock,
) -> None:
    student = _student(engine)
    order = _place(api, student, thali)
    assert _state(engine, order["id"])[2:] == (8, 1)
    now.now = THIRTY_MIN_BEFORE

    response = _cancel(api, student, order)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "CANCELLED"
    assert body["refund"] == {"amount_paise": TWO_THALIS, "status": "SUCCEEDED"}
    assert _state(engine, order["id"]) == (OrderStatus.CANCELLED, 3, 10, 0)
    [refund] = _refunds(engine, order["id"])
    assert (refund.amount_paise, refund.status, refund.attempts) == (
        TWO_THALIS,
        PaymentStatus.SUCCEEDED,
        1,
    )
    # The refund was sent against the placement's authorisation, with its own reference.
    [(reference, _auth_reference, amount)] = gateway.refunded
    assert (reference, amount) == (str(refund.id), TWO_THALIS)


def test_tc_us28_ac2_cancelling_a_preparing_order_refunds_the_late_percentage(
    api: TestClient, engine: Engine, thali: dict[str, Any], now: Clock
) -> None:
    student = _student(engine)
    order = _place(api, student, thali)
    version = _advance(engine, order["id"], OrderStatus.PREPARING)
    now.now = THIRTY_MIN_BEFORE

    response = _cancel(api, student, order, version=version)

    assert response.status_code == 200, response.text
    # P-LATE_REFUND_PCT is 50 %.
    assert response.json()["refund"] == {"amount_paise": 8000, "status": "SUCCEEDED"}
    # The seat comes back; the portions are already being cooked and do not.
    assert _state(engine, order["id"])[::2] == (OrderStatus.CANCELLED, 8)
    assert _state(engine, order["id"])[3] == 0


def test_tc_us28_ac3_cancelling_inside_the_cutoff_is_refused(
    api: TestClient, engine: Engine, thali: dict[str, Any], now: Clock
) -> None:
    student = _student(engine)
    order = _place(api, student, thali)
    now.now = INSIDE_CUTOFF

    response = _cancel(api, student, order)

    assert response.status_code == 409
    assert response.json()["detail"]["message"] == "the cancellation cut-off has passed"
    assert _state(engine, order["id"]) == (OrderStatus.ACCEPTED, 2, 8, 1)
    assert _refunds(engine, order["id"]) == []


def test_tc_us28_ac4_cancelling_a_ready_order_is_refused(
    api: TestClient, engine: Engine, thali: dict[str, Any], now: Clock
) -> None:
    student = _student(engine)
    order = _place(api, student, thali)
    version = _advance(engine, order["id"], OrderStatus.PREPARING, OrderStatus.READY)
    now.now = THIRTY_MIN_BEFORE

    response = _cancel(api, student, order, version=version)

    assert response.status_code == 409
    assert response.json()["detail"]["status"] == "READY"
    assert _state(engine, order["id"]) == (OrderStatus.READY, version, 8, 1)
    assert _refunds(engine, order["id"]) == []


def test_tc_us28_ac5_two_concurrent_cancels_record_exactly_one_refund(
    api: TestClient, engine: Engine, thali: dict[str, Any], now: Clock
) -> None:
    student = _student(engine)
    order = _place(api, student, thali)
    now.now = THIRTY_MIN_BEFORE

    # Different keys: two separate user actions, not a retry of one.
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: _cancel(api, student, order), range(2)))

    assert sorted(r.status_code for r in responses) == [200, 409]
    assert len(_refunds(engine, order["id"])) == 1
    assert _state(engine, order["id"]) == (OrderStatus.CANCELLED, 3, 10, 0)


def test_concurrent_retries_of_one_cancel_return_the_same_result(
    api: TestClient,
    engine: Engine,
    thali: dict[str, Any],
    gateway: FakePaymentGateway,
    now: Clock,
) -> None:
    student = _student(engine)
    order = _place(api, student, thali)
    now.now = THIRTY_MIN_BEFORE

    with ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(
            pool.map(lambda _: _cancel(api, student, order, key="cancel-once"), range(10))
        )

    assert {r.status_code for r in responses} == {200}
    assert {r.json()["status"] for r in responses} == {"CANCELLED"}
    assert len(_refunds(engine, order["id"])) == 1
    assert len(gateway.refunded) == 1


def test_a_stale_version_is_refused_with_the_new_state_and_refund(
    api: TestClient, engine: Engine, thali: dict[str, Any], now: Clock
) -> None:
    """UC-13 3c: the kitchen started the order after the Student looked."""
    student = _student(engine)
    order = _place(api, student, thali)
    _advance(engine, order["id"], OrderStatus.PREPARING)
    now.now = THIRTY_MIN_BEFORE

    response = _cancel(api, student, order)

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "message": "the order has changed",
        "status": "PREPARING",
        "version": 3,
        "refund_paise": 8000,
    }
    assert _state(engine, order["id"]) == (OrderStatus.PREPARING, 3, 8, 1)
    # Confirming again with the new version goes through.
    assert _cancel(api, student, order, version=3).status_code == 200


@pytest.mark.parametrize("whose", ["another student's", "a non-existent"])
def test_cancelling_an_order_that_is_not_yours_is_not_found_and_logged(
    api: TestClient, engine: Engine, thali: dict[str, Any], now: Clock, whose: str
) -> None:
    owner, intruder = _student(engine), _student(engine)
    order = _place(api, owner, thali)
    now.now = THIRTY_MIN_BEFORE
    target = order if whose.startswith("another") else order | {"id": str(uuid.uuid4())}

    response = _cancel(api, intruder, target)

    assert response.status_code == 404
    assert _state(engine, order["id"]) == (OrderStatus.ACCEPTED, 2, 8, 1)
    with Session(engine) as session:
        event = session.scalars(
            select(AuditLog).where(
                AuditLog.action == "ORDER_ACCESS_DENIED", AuditLog.actor_id == str(intruder.id)
            )
        ).one()
    assert event.actor_id == str(intruder.id)
    assert event.after == {"order_id": target["id"], "operation": "cancel"}


@pytest.mark.parametrize("role", [Role.KITCHEN, Role.ADMIN])
def test_tc_us04_ac2_staff_cannot_cancel_a_students_order(
    api: TestClient, engine: Engine, thali: dict[str, Any], now: Clock, role: Role
) -> None:
    """Kitchen Staff are denied every order-cancellation operation (FR-6).

    An Administrator cancels through the admin endpoint with a reason (FR-38), not this one.
    """
    student, staff = _student(engine), _student(engine, role)
    order = _place(api, student, thali)
    now.now = THIRTY_MIN_BEFORE

    response = _cancel(api, staff, order)

    assert response.status_code == 403
    assert _state(engine, order["id"]) == (OrderStatus.ACCEPTED, 2, 8, 1)
    with Session(engine) as session:
        denied = session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "PERMISSION_DENIED", AuditLog.actor_id == str(staff.id))
        )
    assert denied == 1


def test_a_refund_mockpay_does_not_acknowledge_stays_pending_and_is_never_duplicated(
    api: TestClient,
    engine: Engine,
    thali: dict[str, Any],
    gateway: FakePaymentGateway,
    now: Clock,
) -> None:
    """UC-13 5a: the order stays CANCELLED; the outbox retries the one refund record."""
    student = _student(engine)
    order = _place(api, student, thali)
    now.now = THIRTY_MIN_BEFORE
    gateway.unavailable = True

    first = _cancel(api, student, order, key="cancel")
    repeat = _cancel(api, student, order, key="cancel")

    assert first.status_code == repeat.status_code == 200
    assert first.json()["refund"] == {"amount_paise": TWO_THALIS, "status": "PENDING"}
    assert repeat.json() == first.json()
    [refund] = _refunds(engine, order["id"])
    assert (refund.status, refund.attempts) == (PaymentStatus.PENDING, 1)
    assert _state(engine, order["id"]) == (OrderStatus.CANCELLED, 3, 10, 0)


def test_the_cancel_transition_is_attributed_to_the_student(
    api: TestClient, engine: Engine, thali: dict[str, Any], now: Clock
) -> None:
    student = _student(engine)
    order = _place(api, student, thali)
    now.now = THIRTY_MIN_BEFORE

    assert _cancel(api, student, order).status_code == 200

    with Session(engine) as session:
        last = session.scalars(
            select(OrderTransition)
            .where(OrderTransition.order_id == uuid.UUID(order["id"]))
            .order_by(OrderTransition.id.desc())
            .limit(1)
        ).one()
        released = session.scalars(
            select(AuditLog.actor_id).where(
                AuditLog.action.in_(["PORTIONS_RELEASED", "SEAT_RELEASED"]),
                AuditLog.after["order_id"].astext == order["id"],
            )
        ).all()
    assert (last.from_status, last.to_status) == (OrderStatus.ACCEPTED, OrderStatus.CANCELLED)
    assert (last.actor_id, last.actor_role) == (student.id, Role.STUDENT)
    assert released == [str(student.id)] * 2


@pytest.mark.parametrize(
    ("status", "paid", "expected"),
    [
        (OrderStatus.ACCEPTED, 16000, 16000),
        (OrderStatus.PREPARING, 16000, 8000),
        # Half a paisa rounds up.
        (OrderStatus.PREPARING, 1001, 501),
        (OrderStatus.PREPARING, 0, 0),
    ],
)
def test_cancel_refund_amount(status: OrderStatus, paid: int, expected: int) -> None:
    assert cancel_refund_paise(status, paid, 50) == expected


def test_a_key_reused_for_a_different_cancel_is_unprocessable(
    api: TestClient, engine: Engine, thali: dict[str, Any], now: Clock
) -> None:
    student = _student(engine)
    first, second = _place(api, student, thali), _place(api, student, thali)
    now.now = THIRTY_MIN_BEFORE
    assert _cancel(api, student, first, key="k").status_code == 200

    response = _cancel(api, student, second, key="k")

    assert response.status_code == 422
    assert _state(engine, second["id"])[0] is OrderStatus.ACCEPTED
