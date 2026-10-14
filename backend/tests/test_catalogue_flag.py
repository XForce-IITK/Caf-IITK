"""US-09 (CAFIITK-134, FR-11, FR-12) acceptance tests TC-US09-AC1..AC3 via
POST and DELETE /api/v1/items/{id}/flag."""

import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from typing import Annotated, Any, cast
from zoneinfo import ZoneInfo

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app.core import clock
from app.core.security import create_access_token
from app.db.session import get_session
from app.models.capacity import DailyInventory, ServiceDay, Slot
from app.models.catalogue import MenuItem
from app.models.enums import ItemCategory, ItemStatus, OrderStatus, Role
from app.models.identity import User
from app.models.ordering import Order, OrderLine
from app.models.platform import AuditLog
from app.modules.payments.fake import FakePaymentGateway
from app.modules.payments.gateway import PaymentGateway, TransactionGuardedGateway
from app.modules.payments.mockpay_gateway import get_payment_gateway

IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 10, 6)
# After P-MENU_OPEN (08:00) and before the 12:15 slot stops taking bookings.
NOW = datetime(2026, 10, 6, 9, 0, tzinfo=IST)
REASON = "Gas cylinder ran out"


def _url(item_id: uuid.UUID | str) -> str:
    return f"/api/v1/items/{item_id}/flag"


def _add(engine: Engine, *rows: Any) -> None:
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add_all(rows)


def _headers(engine: Engine, role: Role) -> dict[str, str]:
    user = User(
        id=uuid.uuid4(),
        name=f"{role.value} user",
        email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
        password_hash="unused",
        role=role,
    )
    _add(engine, user)
    return {
        "Authorization": f"Bearer {create_access_token(user.id, user.role)}",
        "Idempotency-Key": uuid.uuid4().hex,
    }


@pytest.fixture
def kitchen(engine: Engine) -> dict[str, str]:
    return _headers(engine, Role.KITCHEN)


@pytest.fixture
def menu(engine: Engine) -> dict[str, Any]:
    """Thali with 20 portions on DAY and one bookable slot."""
    thali = MenuItem(id=uuid.uuid4(), name="Thali", category=ItemCategory.MEAL, price_paise=8000)
    slot = Slot(
        id=uuid.uuid4(),
        service_date=DAY,
        starts_at=datetime(2026, 10, 6, 12, 15, tzinfo=IST),
        ends_at=datetime(2026, 10, 6, 12, 30, tzinfo=IST),
        capacity=30,
    )
    _add(
        engine,
        thali,
        ServiceDay(
            service_date=DAY,
            window_start=time(12, 0),
            window_end=time(14, 30),
            slot_len_min=15,
            default_capacity=30,
        ),
    )
    _add(engine, slot, DailyInventory(item_id=thali.id, service_date=DAY, total=20))
    return {"thali": thali, "slot": slot}


@pytest.fixture
def api(db_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """The API at NOW, paying through a fake gateway that approves everything."""
    monkeypatch.setattr(clock, "now", lambda: NOW)
    gateway: PaymentGateway = FakePaymentGateway()

    def guarded(session: Annotated[Session, Depends(get_session)]) -> PaymentGateway:
        return TransactionGuardedGateway(gateway, session)

    cast(FastAPI, db_client.app).dependency_overrides[get_payment_gateway] = guarded
    return db_client


def _flag(api: TestClient, item_id: uuid.UUID, headers: dict[str, str], **body: Any) -> Any:
    return api.post(_url(item_id), json=body if body else {"reason": REASON}, headers=headers)


def _order(api: TestClient, engine: Engine, menu: dict[str, Any]) -> Any:
    return api.post(
        "/api/v1/orders",
        json={
            "slot_id": str(menu["slot"].id),
            "lines": [{"item_id": str(menu["thali"].id), "qty": 1}],
            "quoted_payable_paise": 8000,
        },
        headers=_headers(engine, Role.STUDENT),
    )


def _menu_entry(api: TestClient, engine: Engine, item: MenuItem) -> dict[str, Any]:
    response = api.get(
        "/api/v1/menu", params={"date": DAY.isoformat()}, headers=_headers(engine, Role.STUDENT)
    )
    assert response.status_code == 200, response.text
    entry: dict[str, Any] = next(i for i in response.json()["items"] if i["id"] == str(item.id))
    return entry


def _stock(engine: Engine, item: MenuItem) -> tuple[int, int]:
    with Session(engine) as session:
        row = session.get(DailyInventory, (item.id, DAY))
        assert row is not None
        return row.total, row.allocated


def _item(engine: Engine, item: MenuItem) -> MenuItem:
    with Session(engine) as session:
        row = session.get(MenuItem, item.id)
        assert row is not None
        return row


def _audits(engine: Engine, item: MenuItem) -> list[AuditLog]:
    """Flag entries for this item; audit_log is not emptied between tests."""
    with Session(engine) as session:
        return list(
            session.scalars(
                select(AuditLog)
                .where(
                    AuditLog.entity_id == str(item.id),
                    AuditLog.action.in_(["ITEM_FLAGGED", "ITEM_UNFLAGGED"]),
                )
                .order_by(AuditLog.id)
            )
        )


def test_tc_us09_ac1_flagged_item_is_unavailable_refuses_orders_and_keeps_its_portions(
    api: TestClient, engine: Engine, kitchen: dict[str, str], menu: dict[str, Any]
) -> None:
    thali = menu["thali"]

    response = _flag(api, thali.id, kitchen)

    assert response.status_code == 200, response.text
    assert response.json()["unavailable"] is True
    assert response.json()["unavailable_reason"] == REASON
    entry = _menu_entry(api, engine, thali)
    assert entry["orderable"] is False
    assert entry["not_orderable_reason"] == "UNAVAILABLE"
    assert entry["available_portions"] == 20
    order = _order(api, engine, menu)
    assert order.status_code == 409, order.text
    assert order.json()["detail"]["item_ids"] == [str(thali.id)]
    assert _stock(engine, thali) == (20, 0)


def test_tc_us09_ac2_accepted_orders_with_the_item_are_unaffected(
    api: TestClient, engine: Engine, kitchen: dict[str, str], menu: dict[str, Any]
) -> None:
    placed = _order(api, engine, menu)
    assert placed.status_code == 201, placed.text
    order_id = uuid.UUID(placed.json()["id"])

    assert _flag(api, menu["thali"].id, kitchen).status_code == 200

    with Session(engine) as session:
        order = session.get(Order, order_id)
        assert order is not None
        assert order.status is OrderStatus.ACCEPTED
        lines = session.scalars(select(OrderLine).where(OrderLine.order_id == order_id)).all()
        assert [(line.item_id, line.qty) for line in lines] == [(menu["thali"].id, 1)]
    assert _stock(engine, menu["thali"]) == (20, 1)


def test_tc_us09_ac3_clearing_the_flag_makes_the_item_orderable_again(
    api: TestClient, engine: Engine, kitchen: dict[str, str], menu: dict[str, Any]
) -> None:
    thali = menu["thali"]
    _flag(api, thali.id, kitchen)

    response = api.delete(_url(thali.id), headers=kitchen)

    assert response.status_code == 200, response.text
    assert response.json()["unavailable"] is False
    assert response.json()["unavailable_reason"] is None
    assert _menu_entry(api, engine, thali)["orderable"] is True
    assert _order(api, engine, menu).status_code == 201


def test_flag_and_clear_are_audited_with_the_reason_and_actor(
    api: TestClient, engine: Engine, kitchen: dict[str, str], menu: dict[str, Any]
) -> None:
    thali = menu["thali"]

    _flag(api, thali.id, kitchen)
    api.delete(_url(thali.id), headers=kitchen)

    flagged, cleared = _audits(engine, thali)
    assert flagged.action == "ITEM_FLAGGED"
    assert flagged.actor_role == "KITCHEN"
    assert flagged.before is not None and flagged.before["unavailable"] is False
    assert flagged.after == {
        "unavailable": True,
        "reason": REASON,
        "source": "STAFF",
        "until": None,
    }
    assert cleared.action == "ITEM_UNFLAGGED"
    assert cleared.before == flagged.after
    assert cleared.after is not None and cleared.after["unavailable"] is False


def test_flag_records_its_source_in_the_item(
    api: TestClient, engine: Engine, kitchen: dict[str, str], menu: dict[str, Any]
) -> None:
    _flag(api, menu["thali"].id, kitchen)

    item = _item(engine, menu["thali"])
    assert (item.unavailable, item.unavailable_reason, item.unavailable_source) == (
        True,
        REASON,
        "STAFF",
    )
    assert item.unavailable_until is None


def test_flagging_again_replaces_the_reason(
    api: TestClient, engine: Engine, kitchen: dict[str, str], menu: dict[str, Any]
) -> None:
    _flag(api, menu["thali"].id, kitchen)

    response = _flag(api, menu["thali"].id, kitchen, reason="Paneer delivery late")

    assert response.status_code == 200
    assert _item(engine, menu["thali"]).unavailable_reason == "Paneer delivery late"


def test_clearing_an_unflagged_item_changes_nothing(
    api: TestClient, engine: Engine, kitchen: dict[str, str], menu: dict[str, Any]
) -> None:
    response = api.delete(_url(menu["thali"].id), headers=kitchen)

    assert response.status_code == 200
    assert response.json()["unavailable"] is False
    assert _audits(engine, menu["thali"]) == []


def test_flag_with_an_end_time_is_replaced_by_an_open_ended_one(
    api: TestClient, engine: Engine, kitchen: dict[str, str], menu: dict[str, Any]
) -> None:
    """A staff flag lasts until it is cleared, even over a proposal's flag that would lapse."""
    with Session(engine) as session, session.begin():
        item = session.get(MenuItem, menu["thali"].id)
        assert item is not None
        item.unavailable = True
        item.unavailable_until = NOW + timedelta(hours=1)

    _flag(api, menu["thali"].id, kitchen)

    assert _item(engine, menu["thali"]).unavailable_until is None


def test_administrator_can_flag_and_clear(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    admin = _headers(engine, Role.ADMIN)

    assert _flag(api, menu["thali"].id, admin).status_code == 200
    assert api.delete(_url(menu["thali"].id), headers=admin).status_code == 200


def test_students_cannot_flag_or_clear(
    api: TestClient, engine: Engine, kitchen: dict[str, str], menu: dict[str, Any]
) -> None:
    student = _headers(engine, Role.STUDENT)
    _flag(api, menu["thali"].id, kitchen)

    assert _flag(api, menu["thali"].id, student, reason="no").status_code == 403
    assert api.delete(_url(menu["thali"].id), headers=student).status_code == 403
    assert _item(engine, menu["thali"]).unavailable_reason == REASON


def test_flag_requires_a_login(api: TestClient, menu: dict[str, Any]) -> None:
    assert api.post(_url(menu["thali"].id), json={"reason": REASON}).status_code == 401
    assert api.delete(_url(menu["thali"].id)).status_code == 401


@pytest.mark.parametrize("body", [{}, {"reason": ""}, {"reason": "   "}, {"reason": "x" * 201}])
def test_flag_needs_a_reason(
    api: TestClient,
    engine: Engine,
    kitchen: dict[str, str],
    menu: dict[str, Any],
    body: dict[str, Any],
) -> None:
    response = api.post(_url(menu["thali"].id), json=body, headers=kitchen)

    assert response.status_code == 422
    assert _item(engine, menu["thali"]).unavailable is False


def test_unknown_item_is_404(api: TestClient, kitchen: dict[str, str]) -> None:
    assert _flag(api, uuid.uuid4(), kitchen).status_code == 404
    assert api.delete(_url(uuid.uuid4()), headers=kitchen).status_code == 404


def test_removed_item_is_409(
    api: TestClient, engine: Engine, kitchen: dict[str, str], menu: dict[str, Any]
) -> None:
    with Session(engine) as session, session.begin():
        item = session.get(MenuItem, menu["thali"].id)
        assert item is not None
        item.status = ItemStatus.REMOVED

    assert _flag(api, menu["thali"].id, kitchen).status_code == 409
    assert api.delete(_url(menu["thali"].id), headers=kitchen).status_code == 409
    assert _item(engine, menu["thali"]).unavailable is False


@pytest.fixture
def key_share_lock(engine: Engine, menu: dict[str, Any]) -> Iterator[None]:
    """Hold FOR KEY SHARE on the item, as an order being placed does through order_lines."""
    with engine.connect() as connection, connection.begin():
        connection.execute(
            text("SELECT id FROM menu_items WHERE id = :id FOR KEY SHARE"),
            {"id": menu["thali"].id},
        )
        yield


def test_flagging_does_not_wait_for_orders_in_flight(
    api: TestClient, kitchen: dict[str, str], menu: dict[str, Any], key_share_lock: None
) -> None:
    # Not a `with` block: on failure the request is still blocked, and waiting for it
    # here would hang, since the lock is released only after the test returns.
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        response = pool.submit(_flag, api, menu["thali"].id, kitchen).result(timeout=10)
    finally:
        pool.shutdown(wait=False)

    assert response.status_code == 200
