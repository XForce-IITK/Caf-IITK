"""US-08 (CAFIITK-133, FR-10) acceptance tests TC-US08-AC1..AC3 via DELETE /admin/items/{id}."""

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
from app.models.enums import ItemCategory, ItemStatus, Role
from app.models.identity import User
from app.models.platform import AuditLog
from app.modules.payments.fake import FakePaymentGateway
from app.modules.payments.gateway import PaymentGateway, TransactionGuardedGateway
from app.modules.payments.mockpay_gateway import get_payment_gateway

IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 10, 6)
# After P-MENU_OPEN (08:00) and before the 12:15 slot stops taking bookings (12:00).
NOW = datetime(2026, 10, 6, 9, 0, tzinfo=IST)


def _url(item_id: object) -> str:
    return f"/api/v1/admin/items/{item_id}"


def _add(engine: Engine, *rows: Any) -> None:
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add_all(rows)


def _user(engine: Engine, role: Role) -> User:
    user = User(
        id=uuid.uuid4(),
        name=f"{role.value} user",
        email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
        password_hash="unused",
        role=role,
    )
    _add(engine, user)
    return user


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


@pytest.fixture
def admin(engine: Engine) -> dict[str, str]:
    return _auth(_user(engine, Role.ADMIN))


@pytest.fixture
def student(engine: Engine) -> dict[str, str]:
    return _auth(_user(engine, Role.STUDENT))


@pytest.fixture
def thali(engine: Engine) -> MenuItem:
    item = MenuItem(id=uuid.uuid4(), name="Thali", category=ItemCategory.MEAL, price_paise=8000)
    _add(engine, item)
    return item


@pytest.fixture
def slot(
    db_client: TestClient, engine: Engine, thali: MenuItem, monkeypatch: pytest.MonkeyPatch
) -> Slot:
    """A service day with one slot and Thali portions, the clock and an approving gateway."""
    slot = Slot(
        id=uuid.uuid4(),
        service_date=DAY,
        starts_at=datetime(2026, 10, 6, 12, 15, tzinfo=IST),
        ends_at=datetime(2026, 10, 6, 12, 30, tzinfo=IST),
        capacity=30,
    )
    _add(
        engine,
        ServiceDay(
            service_date=DAY,
            window_start=time(12, 0),
            window_end=time(14, 30),
            slot_len_min=15,
            default_capacity=30,
        ),
    )
    _add(engine, slot, DailyInventory(item_id=thali.id, service_date=DAY, total=10))
    monkeypatch.setattr(clock, "now", lambda: NOW)
    gateway = FakePaymentGateway()

    def guarded(session: Annotated[Session, Depends(get_session)]) -> PaymentGateway:
        return TransactionGuardedGateway(gateway, session)

    cast(FastAPI, db_client.app).dependency_overrides[get_payment_gateway] = guarded
    return slot


def _place(client: TestClient, student: dict[str, str], slot: Slot, item: MenuItem) -> Any:
    return client.post(
        "/api/v1/orders",
        json={
            "slot_id": str(slot.id),
            "lines": [{"item_id": str(item.id), "qty": 1}],
            "quoted_payable_paise": 8000,
        },
        headers=student | {"Idempotency-Key": uuid.uuid4().hex},
    )


def _stored(engine: Engine, item: MenuItem) -> MenuItem | None:
    with Session(engine) as session:
        return session.get(MenuItem, item.id)


def _audit(engine: Engine, item: MenuItem) -> list[AuditLog]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(AuditLog)
                .where(AuditLog.entity_type == "menu_item", AuditLog.entity_id == str(item.id))
                .order_by(AuditLog.id)
            )
        )


def test_tc_us08_ac1_removed_item_leaves_the_menu_and_ordering_it_is_409(
    db_client: TestClient,
    admin: dict[str, str],
    student: dict[str, str],
    thali: MenuItem,
    slot: Slot,
) -> None:
    response = db_client.delete(_url(thali.id), headers=admin)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "REMOVED"
    menu = db_client.get("/api/v1/menu", params={"date": DAY.isoformat()}, headers=student)
    assert menu.json()["items"] == []
    ordered = _place(db_client, student, slot, thali)
    assert ordered.status_code == 409, ordered.text
    assert ordered.json()["detail"]["item_ids"] == [str(thali.id)]


def test_tc_us08_ac2_accepted_order_proceeds_to_picked_up_and_keeps_the_item(
    db_client: TestClient,
    engine: Engine,
    admin: dict[str, str],
    student: dict[str, str],
    thali: MenuItem,
    slot: Slot,
) -> None:
    placed = _place(db_client, student, slot, thali)
    assert placed.status_code == 201, placed.text
    order_id = placed.json()["id"]

    assert db_client.delete(_url(thali.id), headers=admin).status_code == 200

    cook = _auth(_user(engine, Role.KITCHEN))
    queue = db_client.get("/api/v1/kitchen/queue", headers=cook)
    assert queue.status_code == 200, queue.text
    assert "Thali" in queue.text
    for action in ["START", "READY", "PICKED_UP"]:
        moved = db_client.post(
            f"/api/v1/kitchen/orders/{order_id}/transitions", json={"action": action}, headers=cook
        )
        assert moved.status_code == 200, moved.text
    order = db_client.get(f"/api/v1/orders/{order_id}", headers=student).json()
    assert order["status"] == "PICKED_UP"
    assert [h["to_status"] for h in order["history"]][-1] == "PICKED_UP"
    [snapshot] = order["snapshots"]
    assert [(line["name"], line["unit_price_paise"]) for line in snapshot["price"]["lines"]] == [
        ("Thali", 8000)
    ]


def test_tc_us08_ac3_removed_item_row_still_exists_as_removed(
    db_client: TestClient, engine: Engine, admin: dict[str, str], thali: MenuItem
) -> None:
    db_client.delete(_url(thali.id), headers=admin)

    stored = _stored(engine, thali)
    assert stored is not None
    assert (stored.name, stored.status, stored.price_paise) == ("Thali", ItemStatus.REMOVED, 8000)


def test_removal_is_audited_once_and_repeating_it_is_a_no_op(
    db_client: TestClient, engine: Engine, admin: dict[str, str], thali: MenuItem
) -> None:
    assert db_client.delete(_url(thali.id), headers=admin).status_code == 200
    again = db_client.delete(_url(thali.id), headers=admin)

    assert again.status_code == 200
    assert again.json()["status"] == "REMOVED"
    [entry] = _audit(engine, thali)
    assert (entry.action, entry.actor_role) == ("ITEM_REMOVED", "ADMIN")
    assert (entry.before, entry.after) == ({"status": "ACTIVE"}, {"status": "REMOVED"})


def test_removed_item_cannot_be_edited_or_flagged(
    db_client: TestClient, admin: dict[str, str], thali: MenuItem
) -> None:
    db_client.delete(_url(thali.id), headers=admin)

    assert (
        db_client.patch(_url(thali.id), json={"price_paise": 9000}, headers=admin).status_code
        == 409
    )
    flag = db_client.post(f"/api/v1/items/{thali.id}/flag", json={"reason": "x"}, headers=admin)
    assert flag.status_code == 409


def test_unknown_item_is_404(db_client: TestClient, admin: dict[str, str]) -> None:
    assert db_client.delete(_url(uuid.uuid4()), headers=admin).status_code == 404


@pytest.mark.parametrize("role", [Role.KITCHEN, Role.STUDENT])
def test_only_the_administrator_can_remove_items(
    db_client: TestClient, engine: Engine, thali: MenuItem, role: Role
) -> None:
    response = db_client.delete(_url(thali.id), headers=_auth(_user(engine, role)))

    assert response.status_code == 403
    stored = _stored(engine, thali)
    assert stored is not None and stored.status is ItemStatus.ACTIVE


def test_removing_requires_a_token(db_client: TestClient, engine: Engine, thali: MenuItem) -> None:
    assert db_client.delete(_url(thali.id)).status_code == 401
    stored = _stored(engine, thali)
    assert stored is not None and stored.status is ItemStatus.ACTIVE
