"""US-27 (FR-35, FR-36, FR-39) acceptance tests TC-US27-AC1..AC5 through
PATCH /api/v1/orders/{id}, plus the modification quote, the subsidy a re-priced
order keeps, and refunds split across the order's authorisations.

The kitchen "start" endpoint (US-34) is not merged yet, so AC5 moves the order to
PREPARING through the order state machine, as the kitchen will.
"""

import uuid
from datetime import date, datetime, time
from typing import Annotated, Any, cast
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.core import clock
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
from app.models.ordering import (
    Order,
    OrderLine,
    OrderModification,
    OrderTransition,
    Payment,
    PriceSnapshot,
)
from app.models.platform import AuditLog
from app.modules.ordering.refunds import InsufficientChargesError, RefundPart, refund_parts
from app.modules.ordering.state_machine import transition
from app.modules.payments.fake import FakePaymentGateway
from app.modules.payments.gateway import (
    AuthOutcome,
    PaymentGateway,
    TransactionGuardedGateway,
)
from app.modules.payments.mockpay_gateway import MockpayGateway, get_payment_gateway

IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 10, 6)
NOW = datetime(2026, 10, 6, 9, 0, tzinfo=IST)
# The 12:15 slot's cut-off is 12:05 (P-CUTOFF 10 min).
INSIDE_CUTOFF = datetime(2026, 10, 6, 12, 10, tzinfo=IST)
THALI, TEA = 8000, 1500


@pytest.fixture
def menu(engine: Engine) -> dict[str, Any]:
    """Thali (10), Tea (10), sold-out Samosa; the 12:15 and 13:00 slots of 30 seats."""
    thali = MenuItem(id=uuid.uuid4(), name="Thali", category=ItemCategory.MEAL, price_paise=THALI)
    tea = MenuItem(id=uuid.uuid4(), name="Tea", category=ItemCategory.BEVERAGE, price_paise=TEA)
    samosa = MenuItem(id=uuid.uuid4(), name="Samosa", category=ItemCategory.SNACK, price_paise=2000)
    day = ServiceDay(
        service_date=DAY,
        window_start=time(12, 0),
        window_end=time(14, 30),
        slot_len_min=15,
        default_capacity=30,
    )
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
    other_day = ServiceDay(
        service_date=date(2026, 10, 7),
        window_start=time(12, 0),
        window_end=time(14, 30),
        slot_len_min=15,
        default_capacity=30,
    )
    tomorrow = Slot(
        id=uuid.uuid4(),
        service_date=date(2026, 10, 7),
        starts_at=datetime(2026, 10, 7, 12, 15, tzinfo=IST),
        ends_at=datetime(2026, 10, 7, 12, 30, tzinfo=IST),
        capacity=30,
    )
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add_all([thali, tea, samosa, day, other_day])
        session.flush()
        session.add_all(
            [
                early,
                late,
                tomorrow,
                DailyInventory(item_id=thali.id, service_date=DAY, total=10),
                DailyInventory(item_id=tea.id, service_date=DAY, total=10),
                DailyInventory(item_id=samosa.id, service_date=DAY, total=0),
            ]
        )
    return {
        "thali": thali,
        "tea": tea,
        "samosa": samosa,
        "early": early,
        "late": late,
        "tomorrow": tomorrow,
    }


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


def _use_gateway(client: TestClient, gateway: PaymentGateway) -> None:
    def guarded(session: Annotated[Session, Depends(get_session)]) -> PaymentGateway:
        # The guard proves no payment call is made with a transaction open (NFR-6).
        return TransactionGuardedGateway(gateway, session)

    cast(FastAPI, client.app).dependency_overrides[get_payment_gateway] = guarded


@pytest.fixture
def gateway(db_client: TestClient) -> FakePaymentGateway:
    fake = FakePaymentGateway()
    _use_gateway(db_client, fake)
    return fake


@pytest.fixture
def api(db_client: TestClient, gateway: FakePaymentGateway, now: Clock) -> TestClient:
    return db_client


def _student(engine: Engine, role: Role = Role.STUDENT, *, eligible: bool = False) -> User:
    user = User(
        id=uuid.uuid4(),
        name="Asha",
        email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
        password_hash="unused",
        role=role,
        subsidy_eligible=eligible,
    )
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add(user)
    return user


def _headers(user: User, key: str | None = None) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_access_token(user.id, user.role)}",
        "Idempotency-Key": key or uuid.uuid4().hex,
    }


def _cart(menu: dict[str, Any], slot: str = "early", **qty: int) -> dict[str, Any]:
    return {
        "slot_id": str(menu[slot].id),
        "lines": [{"item_id": str(menu[name].id), "qty": q} for name, q in qty.items()],
    }


def _place(api: TestClient, student: User, menu: dict[str, Any], payable: int) -> dict[str, Any]:
    """A Thali and a Tea in the 12:15 slot."""
    response = api.post(
        "/api/v1/orders",
        json=_cart(menu, thali=1, tea=1) | {"quoted_payable_paise": payable},
        headers=_headers(student),
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    assert body["status"] == "ACCEPTED"
    return body


def _modify(
    api: TestClient,
    student: User,
    order: dict[str, Any],
    cart: dict[str, Any],
    payable: int,
    *,
    version: int | None = None,
    key: str | None = None,
) -> Response:
    response: Response = api.patch(
        f"/api/v1/orders/{order['id']}",
        json=cart | {"quoted_payable_paise": payable, "version": version or order["version"]},
        headers=_headers(student, key),
    )
    return response


def _snapshot(engine: Engine, order_id: str) -> dict[str, Any]:
    """Everything that must not change when a modification fails."""
    with Session(engine) as session:
        oid = uuid.UUID(order_id)
        order = session.get_one(Order, oid)
        stock = {row.item_id: row.allocated for row in session.scalars(select(DailyInventory))}
        seats = {row.id: row.booked for row in session.scalars(select(Slot))}
        return {
            "slot_id": order.slot_id,
            "paid_paise": order.paid_paise,
            "lines": {
                line.item_id: line.qty
                for line in session.scalars(select(OrderLine).where(OrderLine.order_id == oid))
            },
            "snapshots": session.scalars(
                select(PriceSnapshot.version).where(PriceSnapshot.order_id == oid)
            ).all(),
            "allocated": stock,
            "booked": seats,
        }


def _payments(engine: Engine, order_id: str, kind: PaymentKind) -> list[Payment]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(Payment)
                .where(Payment.order_id == uuid.UUID(order_id), Payment.kind == kind)
                .order_by(Payment.created_at)
            )
        )


def test_tc_us27_ac1_moving_to_another_slot_swaps_the_seat_and_reprices(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    student = _student(engine)
    order = _place(api, student, menu, THALI + TEA)

    response = _modify(api, student, order, _cart(menu, "late", thali=1, tea=1), THALI + TEA)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["slot_id"], body["difference_paise"]) == (
        "ACCEPTED",
        str(menu["late"].id),
        0,
    )
    assert body["refund"] is None
    after = _snapshot(engine, order["id"])
    assert after["booked"][menu["early"].id] == 0
    assert after["booked"][menu["late"].id] == 1
    # Priced again at modification time and appended as snapshot v2 (FR-27).
    assert after["snapshots"] == [1, 2]
    assert body["price"]["slot_id"] == str(menu["late"].id)
    # Portions of an unchanged cart are untouched.
    assert after["allocated"] == {menu["thali"].id: 1, menu["tea"].id: 1, menu["samosa"].id: 0}


def test_tc_us27_ac2_adding_a_sold_out_item_names_it_and_changes_nothing(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    student = _student(engine)
    order = _place(api, student, menu, THALI + TEA)
    before = _snapshot(engine, order["id"])

    response = _modify(
        api, student, order, _cart(menu, thali=1, tea=1, samosa=1), THALI + TEA + 2000
    )

    assert response.status_code == 409
    assert response.json()["detail"]["item_ids"] == [str(menu["samosa"].id)]
    assert _snapshot(engine, order["id"]) == before


@pytest.mark.parametrize("outcome", [AuthOutcome.DECLINED, AuthOutcome.TIMEOUT])
def test_tc_us27_ac3_a_declined_difference_leaves_the_order_exactly_as_before(
    api: TestClient,
    engine: Engine,
    menu: dict[str, Any],
    gateway: FakePaymentGateway,
    outcome: AuthOutcome,
) -> None:
    student = _student(engine)
    order = _place(api, student, menu, THALI + TEA)
    before = _snapshot(engine, order["id"])
    gateway.outcome = outcome

    # One more Thali and a move to 13:00: both a portion and a seat are taken first.
    response = _modify(api, student, order, _cart(menu, "late", thali=2, tea=1), 2 * THALI + TEA)

    assert response.status_code == 402
    assert response.json()["detail"]["outcome"] == outcome.value
    # Everything reserved for the modification has been released.
    assert _snapshot(engine, order["id"]) == before
    [charge] = [p for p in _payments(engine, order["id"], PaymentKind.AUTH) if p.cause == "MODIFY"]
    assert (charge.amount_paise, charge.status) == (THALI, PaymentStatus.FAILED)
    with Session(engine) as session:
        assert session.scalars(select(OrderModification.status)).one() is (
            ModificationStatus.RELEASED
        )
    # A timed-out authorisation may still have landed, so it is voided (SADD 6.2).
    voids = _payments(engine, order["id"], PaymentKind.VOID)
    assert len(voids) == (1 if outcome is AuthOutcome.TIMEOUT else 0)


def test_tc_us27_ac4_lowering_the_price_records_exactly_one_refund(
    api: TestClient, engine: Engine, menu: dict[str, Any], gateway: FakePaymentGateway
) -> None:
    student = _student(engine)
    order = _place(api, student, menu, THALI + TEA)

    # Drop the Rs 15 Tea; the request is sent twice with one key, as a retry would.
    first = _modify(api, student, order, _cart(menu, thali=1), THALI, key="drop-tea")
    repeat = _modify(api, student, order, _cart(menu, thali=1), THALI, key="drop-tea")

    assert first.status_code == repeat.status_code == 200, first.text
    assert first.json()["refund"] == {"amount_paise": TEA, "status": "SUCCEEDED"}
    assert repeat.json() == first.json()
    [refund] = _payments(engine, order["id"], PaymentKind.REFUND)
    assert (refund.amount_paise, refund.cause) == (TEA, PaymentCause.MODIFY)
    assert len(gateway.refunded) == 1
    after = _snapshot(engine, order["id"])
    assert after["paid_paise"] == THALI
    assert after["allocated"][menu["tea"].id] == 0


def test_tc_us27_ac5_a_preparing_order_cannot_be_modified(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    student = _student(engine)
    order = _place(api, student, menu, THALI + TEA)
    with Session(engine) as session, session.begin():
        row = session.get_one(Order, uuid.UUID(order["id"]), with_for_update=True)
        transition(row.status, OrderStatus.PREPARING)
        session.add(
            OrderTransition(
                order_id=row.id, from_status=row.status, to_status=OrderStatus.PREPARING
            )
        )
        row.status = OrderStatus.PREPARING
        row.version += 1
        version = row.version
    before = _snapshot(engine, order["id"])

    response = _modify(api, student, order, _cart(menu, thali=1), THALI, version=version)

    assert response.status_code == 409
    assert response.json()["detail"]["status"] == "PREPARING"
    assert _snapshot(engine, order["id"]) == before


def test_a_higher_price_is_charged_for_the_difference(
    api: TestClient, engine: Engine, menu: dict[str, Any], gateway: FakePaymentGateway
) -> None:
    student = _student(engine)
    order = _place(api, student, menu, THALI + TEA)

    response = _modify(api, student, order, _cart(menu, thali=2, tea=1), 2 * THALI + TEA)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["difference_paise"], body["paid_paise"]) == (THALI, 2 * THALI + TEA)
    assert gateway.authorised[-1][1] == THALI
    after = _snapshot(engine, order["id"])
    assert after["allocated"][menu["thali"].id] == 2
    assert after["snapshots"] == [1, 2]
    with Session(engine) as session:
        assert session.scalars(select(OrderModification.status)).one() is (
            ModificationStatus.APPLIED
        )


def test_the_order_keeps_its_own_subsidy_when_repriced(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    """FR-24 step 4: the order being modified does not count as another subsidised order."""
    student = _student(engine, eligible=True)
    # Rs 95 less the Rs 20 subsidy.
    order = _place(api, student, menu, THALI + TEA - 2000)

    quote = api.post(
        f"/api/v1/orders/{order['id']}/quote",
        json=_cart(menu, thali=1),
        headers=_headers(student),
    )
    assert quote.status_code == 200, quote.text
    assert quote.json()["quote"]["subsidy_paise"] == 2000
    assert quote.json()["difference_paise"] == -TEA

    response = _modify(api, student, order, _cart(menu, thali=1), THALI - 2000)

    assert response.status_code == 200, response.text
    assert response.json()["refund"]["amount_paise"] == TEA
    assert response.json()["subsidy_applied"] is True


def test_cancelling_after_a_price_rise_refunds_each_authorisation_within_its_amount(
    db_client: TestClient, engine: Engine, menu: dict[str, Any], now: Clock, mockpay_url: str
) -> None:
    """Against real mockpay, which refuses a refund above one authorisation's amount."""
    with httpx.Client(base_url=mockpay_url, timeout=5) as client:
        _use_gateway(db_client, MockpayGateway(client))
        student = _student(engine)
        order = _place(db_client, student, menu, THALI + TEA)
        raised = _modify(db_client, student, order, _cart(menu, thali=2, tea=1), 2 * THALI + TEA)
        assert raised.status_code == 200, raised.text

        cancelled = db_client.post(
            f"/api/v1/orders/{order['id']}/cancel",
            json={"version": raised.json()["version"]},
            headers=_headers(student),
        )

        assert cancelled.status_code == 200, cancelled.text
        # Rs 175 refunded as Rs 95 from the placement and Rs 80 from the rise.
        assert cancelled.json()["refund"] == {
            "amount_paise": 2 * THALI + TEA,
            "status": "SUCCEEDED",
        }


def test_modifying_inside_the_cutoff_is_refused(
    api: TestClient, engine: Engine, menu: dict[str, Any], now: Clock
) -> None:
    student = _student(engine)
    order = _place(api, student, menu, THALI + TEA)
    now.now = INSIDE_CUTOFF

    response = _modify(api, student, order, _cart(menu, thali=1), THALI)

    assert response.status_code == 409
    assert response.json()["detail"]["message"] == "the modification cut-off has passed"


def test_a_stale_version_is_refused(api: TestClient, engine: Engine, menu: dict[str, Any]) -> None:
    student = _student(engine)
    order = _place(api, student, menu, THALI + TEA)
    assert _modify(api, student, order, _cart(menu, thali=1), THALI).status_code == 200

    # Still the version the Student saw before the first modification.
    response = _modify(api, student, order, _cart(menu, thali=2), 2 * THALI)

    assert response.status_code == 409
    assert response.json()["detail"]["message"] == "the order has changed"


@pytest.mark.parametrize(
    ("cart", "message"),
    [
        (lambda menu: _cart(menu, thali=1, tea=1), "The order already has these items and slot"),
        (
            lambda menu: _cart(menu, "tomorrow", thali=1, tea=1),
            "The new slot must be on the same day",
        ),
    ],
)
def test_nothing_to_change_or_another_day_is_unprocessable(
    api: TestClient, engine: Engine, menu: dict[str, Any], cart: Any, message: str
) -> None:
    student = _student(engine)
    order = _place(api, student, menu, THALI + TEA)

    response = _modify(api, student, order, cart(menu), THALI + TEA)

    assert response.status_code == 422
    assert response.json()["detail"] == message


def test_another_students_order_is_not_found_and_logged(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    owner, intruder = _student(engine), _student(engine)
    order = _place(api, owner, menu, THALI + TEA)
    before = _snapshot(engine, order["id"])

    response = _modify(api, intruder, order, _cart(menu, thali=1), THALI)

    assert response.status_code == 404
    assert _snapshot(engine, order["id"]) == before
    with Session(engine) as session:
        event = session.scalars(
            select(AuditLog).where(
                AuditLog.action == "ORDER_ACCESS_DENIED", AuditLog.actor_id == str(intruder.id)
            )
        ).one()
    assert event.after == {"order_id": order["id"], "operation": "modify"}


def test_kitchen_staff_cannot_modify_a_students_order(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    student, cook = _student(engine), _student(engine, Role.KITCHEN)
    order = _place(api, student, menu, THALI + TEA)

    assert _modify(api, cook, order, _cart(menu, thali=1), THALI).status_code == 403


def test_the_modification_appears_in_the_order_history(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    student = _student(engine)
    order = _place(api, student, menu, THALI + TEA)
    assert _modify(api, student, order, _cart(menu, thali=1), THALI).status_code == 200

    history = api.get(f"/api/v1/orders/{order['id']}", headers=_headers(student)).json()["history"]

    assert history[-1] | {"at": None} == {
        "from_status": "ACCEPTED",
        "to_status": "ACCEPTED",
        "at": None,
        "actor_role": "STUDENT",
        "reason": "modified",
    }


A, B, C = (uuid.UUID(int=n) for n in (1, 2, 3))
R1, R2 = (uuid.UUID(int=n) for n in (11, 12))


@pytest.mark.parametrize(
    ("charges", "refunds", "refund_id", "expected"),
    [
        # One authorisation: the record id is the reference.
        ([(A, 9500)], [(R1, 1500)], R1, [RefundPart(str(R1), A, 1500)]),
        # A second refund continues where the first stopped, then spills into B.
        (
            [(A, 9500), (B, 8000)],
            [(R1, 1500), (R2, 16000)],
            R2,
            [RefundPart(f"{R2}:1", A, 8000), RefundPart(f"{R2}:2", B, 8000)],
        ),
        # A later authorisation never changes an earlier refund's parts.
        ([(A, 9500), (B, 8000), (C, 100)], [(R1, 1500)], R1, [RefundPart(str(R1), A, 1500)]),
        # Nothing to send for a zero refund.
        ([(A, 9500)], [(R1, 0)], R1, []),
    ],
)
def test_refund_parts(
    charges: list[tuple[uuid.UUID, int]],
    refunds: list[tuple[uuid.UUID, int]],
    refund_id: uuid.UUID,
    expected: list[RefundPart],
) -> None:
    assert refund_parts(charges, refunds, refund_id) == expected


def test_refund_parts_refuse_more_than_was_charged() -> None:
    with pytest.raises(InsufficientChargesError):
        refund_parts([(A, 100)], [(R1, 101)], R1)
    with pytest.raises(ValueError, match="not among"):
        refund_parts([(A, 100)], [(R1, 1)], R2)


def test_an_order_cancelled_while_the_difference_is_charged_keeps_nothing(
    db_client: TestClient, engine: Engine, menu: dict[str, Any], now: Clock
) -> None:
    """The charge lands after the order changed: the hold is released and the charge voided."""

    class CancelledMeanwhile(FakePaymentGateway):
        def authorise(self, reference: str, amount_paise: int) -> Any:
            if self.authorised:  # the placement's own charge goes through untouched
                with Session(engine) as session, session.begin():
                    order = session.scalars(select(Order).with_for_update()).one()
                    order.status = OrderStatus.CANCELLED
            return super().authorise(reference, amount_paise)

    _use_gateway(db_client, CancelledMeanwhile())
    student = _student(engine)
    order = _place(db_client, student, menu, THALI + TEA)

    response = _modify(db_client, student, order, _cart(menu, thali=2, tea=1), 2 * THALI + TEA)

    assert response.status_code == 409
    after = _snapshot(engine, order["id"])
    assert after["allocated"][menu["thali"].id] == 1
    assert after["snapshots"] == [1]
    [void] = _payments(engine, order["id"], PaymentKind.VOID)
    assert (void.cause, void.amount_paise) == (PaymentCause.MODIFY, THALI)


def test_a_full_slot_or_a_changed_price_is_refused(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    student = _student(engine)
    order = _place(api, student, menu, THALI + TEA)
    with Session(engine) as session, session.begin():
        session.get_one(Slot, menu["late"].id).booked = 30

    full = _modify(api, student, order, _cart(menu, "late", thali=1, tea=1), THALI + TEA)
    stale_quote = _modify(api, student, order, _cart(menu, thali=2, tea=1), THALI)

    assert full.status_code == 409
    assert full.json()["detail"]["slot_id"] == str(menu["late"].id)
    assert stale_quote.status_code == 409
    assert stale_quote.json()["detail"]["quote"]["payable_paise"] == 2 * THALI + TEA


@pytest.mark.parametrize(
    ("change", "status"),
    [
        (lambda menu: _cart(menu, thali=4), 422),  # above P-MAX_QTY
        (lambda menu: {"slot_id": str(uuid.uuid4()), "lines": _cart(menu, thali=1)["lines"]}, 404),
        (
            lambda menu: {
                "slot_id": str(menu["early"].id),
                "lines": [{"item_id": str(uuid.uuid4()), "qty": 1}],
            },
            422,
        ),
    ],
    ids=["too-many", "unknown-slot", "unknown-item"],
)
def test_invalid_carts_are_refused_by_quote_and_modify(
    api: TestClient, engine: Engine, menu: dict[str, Any], change: Any, status: int
) -> None:
    student = _student(engine)
    order = _place(api, student, menu, THALI + TEA)
    before = _snapshot(engine, order["id"])

    quote = api.post(
        f"/api/v1/orders/{order['id']}/quote", json=change(menu), headers=_headers(student)
    )
    modified = _modify(api, student, order, change(menu), THALI)

    assert (quote.status_code, modified.status_code) == (status, status)
    assert _snapshot(engine, order["id"]) == before


def test_quoting_another_students_order_is_not_found(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    owner, intruder = _student(engine), _student(engine)
    order = _place(api, owner, menu, THALI + TEA)

    response = api.post(
        f"/api/v1/orders/{order['id']}/quote", json=_cart(menu, thali=1), headers=_headers(intruder)
    )

    assert response.status_code == 404


def test_a_key_reused_for_a_different_modification_is_unprocessable(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    student = _student(engine)
    order = _place(api, student, menu, THALI + TEA)
    assert _modify(api, student, order, _cart(menu, thali=1), THALI, key="k").status_code == 200

    response = _modify(api, student, order, _cart(menu, thali=2), 2 * THALI, key="k")

    assert response.status_code == 422


def test_charged_moves_in_opposite_directions_take_the_slots_in_one_order(
    db_client: TestClient, engine: Engine, menu: dict[str, Any], now: Clock, monkeypatch: Any
) -> None:
    """NFR-4: two price-raising modifies swap slots at the same moment. Updating
    orders.slot_id takes a key-share lock on the new slot through its foreign key, so
    settling must hold both slots in ascending id order or the two deadlock."""
    import threading

    from app.modules.ordering import retry

    deadlocks: list[str] = []
    real = retry.is_transient

    def recording(exc: Any) -> bool:
        if getattr(exc.orig, "sqlstate", None) == "40P01":
            deadlocks.append(str(exc.orig))
        return real(exc)

    monkeypatch.setattr(retry, "is_transient", recording)
    rounds = 5
    barrier = threading.Barrier(2, timeout=30)

    class SettleTogether(FakePaymentGateway):
        """Holds each charge for a difference until its partner arrives."""

        def authorise(self, reference: str, amount_paise: int) -> Any:
            if amount_paise == TEA:
                barrier.wait()
            return super().authorise(reference, amount_paise)

    _use_gateway(db_client, SettleTogether())
    # Each round takes four Teas; the fixture stocks ten.
    with Session(engine) as session, session.begin():
        session.get_one(DailyInventory, (menu["tea"].id, DAY)).total = 100
    for _ in range(rounds):
        early_student, late_student = _student(engine), _student(engine)
        early = _place(db_client, early_student, menu, THALI + TEA)
        late_cart = _cart(menu, "late", thali=1, tea=1) | {"quoted_payable_paise": THALI + TEA}
        late = db_client.post(
            "/api/v1/orders", json=late_cart, headers=_headers(late_student)
        ).json()
        # Each adds a Tea (+Rs 15) and swaps to the other slot.
        moves = [
            (early_student, early, _cart(menu, "late", thali=1, tea=2)),
            (late_student, late, _cart(menu, "early", thali=1, tea=2)),
        ]
        results: list[int] = []
        threads = [
            threading.Thread(
                target=lambda s=s, o=o, c=c, out=results: out.append(
                    _modify(db_client, s, o, c, THALI + 2 * TEA).status_code
                )
            )
            for s, o, c in moves
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        assert results == [200, 200]

    assert deadlocks == []
    assert _snapshot(engine, early["id"])["booked"] == {
        menu["early"].id: rounds,
        menu["late"].id: rounds,
        menu["tomorrow"].id: 0,
    }
