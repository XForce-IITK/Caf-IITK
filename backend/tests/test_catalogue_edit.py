"""US-07 (CAFIITK-132, FR-9) acceptance test TC-US07-AC1 via PATCH /api/v1/admin/items/{id}.

Also US-04 AC1 on the real endpoint: Kitchen Staff cannot change a price.
"""

import uuid
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
from app.models.enums import ItemCategory, ItemStatus, Role
from app.models.identity import User
from app.models.ordering import PriceSnapshot
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
def thali(engine: Engine) -> MenuItem:
    item = MenuItem(
        id=uuid.uuid4(),
        name="Thali",
        description="Dal, rice, two rotis",
        category=ItemCategory.MEAL,
        price_paise=8000,
    )
    _add(engine, item)
    return item


def _stored(engine: Engine, item: MenuItem) -> MenuItem:
    with Session(engine) as session:
        return session.scalars(select(MenuItem).where(MenuItem.id == item.id)).one()


def _audit(engine: Engine, item: MenuItem) -> list[AuditLog]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(AuditLog)
                .where(AuditLog.entity_type == "menu_item", AuditLog.entity_id == str(item.id))
                .order_by(AuditLog.id)
            )
        )


@pytest.fixture
def ordering(
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


def test_tc_us07_ac1_price_change_keeps_the_snapshot_and_new_quotes_use_it(
    db_client: TestClient,
    engine: Engine,
    admin: dict[str, str],
    thali: MenuItem,
    ordering: Slot,
) -> None:
    student = _auth(_user(engine, Role.STUDENT))
    cart = {"slot_id": str(ordering.id), "lines": [{"item_id": str(thali.id), "qty": 1}]}
    placed = db_client.post(
        "/api/v1/orders",
        json=cart | {"quoted_payable_paise": 8000},
        headers=student | {"Idempotency-Key": uuid.uuid4().hex},
    )
    assert placed.status_code == 201, placed.text
    order_id = placed.json()["id"]

    response = db_client.patch(_url(thali.id), json={"price_paise": 9000}, headers=admin)

    assert response.status_code == 200, response.text
    assert response.json()["price_paise"] == 9000
    order = db_client.get(f"/api/v1/orders/{order_id}", headers=student).json()
    assert order["price"]["payable_paise"] == 8000
    assert [s["price"]["lines"][0]["unit_price_paise"] for s in order["snapshots"]] == [8000]
    with Session(engine) as session:
        stored = session.scalars(
            select(PriceSnapshot).where(PriceSnapshot.order_id == uuid.UUID(order_id))
        ).all()
    assert [(s.version, s.payable_paise) for s in stored] == [(1, 8000)]
    quote = db_client.post("/api/v1/quotes", json=cart, headers=student)
    assert quote.status_code == 200, quote.text
    assert quote.json()["payable_paise"] == 9000


def test_new_price_appears_on_the_menu(
    db_client: TestClient, engine: Engine, admin: dict[str, str], thali: MenuItem
) -> None:
    db_client.patch(_url(thali.id), json={"price_paise": 9000}, headers=admin)

    menu = db_client.get(
        "/api/v1/menu", params={"date": DAY.isoformat()}, headers=_auth(_user(engine, Role.STUDENT))
    ).json()

    assert [(i["name"], i["price_paise"]) for i in menu["items"]] == [("Thali", 9000)]


def test_description_and_category_can_be_edited_and_other_fields_are_kept(
    db_client: TestClient, engine: Engine, admin: dict[str, str], thali: MenuItem
) -> None:
    response = db_client.patch(
        _url(thali.id),
        json={"description": "  Dal, rice, sabzi  ", "category": "SNACK"},
        headers=admin,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["name"], body["description"], body["category"], body["price_paise"]) == (
        "Thali",
        "Dal, rice, sabzi",
        "SNACK",
        8000,
    )
    stored = _stored(engine, thali)
    assert (stored.description, stored.category, stored.price_paise) == (
        "Dal, rice, sabzi",
        ItemCategory.SNACK,
        8000,
    )


def test_edit_is_audited_with_only_the_changed_fields(
    db_client: TestClient, engine: Engine, admin: dict[str, str], thali: MenuItem
) -> None:
    db_client.patch(_url(thali.id), json={"price_paise": 9000, "category": "MEAL"}, headers=admin)

    [entry] = _audit(engine, thali)
    assert entry.action == "ITEM_UPDATED"
    assert entry.actor_role == "ADMIN"
    assert (entry.before, entry.after) == ({"price_paise": 8000}, {"price_paise": 9000})


def test_edit_that_changes_nothing_writes_no_audit(
    db_client: TestClient, engine: Engine, admin: dict[str, str], thali: MenuItem
) -> None:
    response = db_client.patch(_url(thali.id), json={"price_paise": 8000}, headers=admin)

    assert response.status_code == 200
    assert _audit(engine, thali) == []


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"price_paise": 99},
        {"price_paise": 50_001},
        {"price_paise": None},
        {"category": "DRINK"},
        {"description": "x" * 301},
        {"name": "Veg Thali"},  # FR-9: the name is not editable
        {"status": "REMOVED"},  # removal is FR-10's endpoint
    ],
)
def test_invalid_edit_is_422_and_changes_nothing(
    db_client: TestClient,
    engine: Engine,
    admin: dict[str, str],
    thali: MenuItem,
    body: dict[str, Any],
) -> None:
    response = db_client.patch(_url(thali.id), json=body, headers=admin)

    assert response.status_code == 422
    stored = _stored(engine, thali)
    assert (stored.name, stored.price_paise, stored.status) == ("Thali", 8000, ItemStatus.ACTIVE)
    assert _audit(engine, thali) == []


@pytest.mark.parametrize("price_paise", [100, 50_000])
def test_price_boundaries_are_accepted(
    db_client: TestClient, admin: dict[str, str], thali: MenuItem, price_paise: int
) -> None:
    response = db_client.patch(_url(thali.id), json={"price_paise": price_paise}, headers=admin)
    assert response.status_code == 200


def test_unknown_item_is_404(db_client: TestClient, admin: dict[str, str]) -> None:
    response = db_client.patch(_url(uuid.uuid4()), json={"price_paise": 9000}, headers=admin)
    assert response.status_code == 404


def test_removed_item_cannot_be_edited(
    db_client: TestClient, engine: Engine, admin: dict[str, str], thali: MenuItem
) -> None:
    with Session(engine) as session, session.begin():
        session.execute(
            update(MenuItem).where(MenuItem.id == thali.id).values(status=ItemStatus.REMOVED)
        )

    response = db_client.patch(_url(thali.id), json={"price_paise": 9000}, headers=admin)

    assert response.status_code == 409
    assert _stored(engine, thali).price_paise == 8000


def test_tc_us04_ac1_kitchen_cannot_change_a_price_and_it_is_logged(
    db_client: TestClient, engine: Engine, thali: MenuItem
) -> None:
    kitchen = _user(engine, Role.KITCHEN)

    response = db_client.patch(_url(thali.id), json={"price_paise": 100}, headers=_auth(kitchen))

    assert response.status_code == 403
    assert _stored(engine, thali).price_paise == 8000
    assert _audit(engine, thali) == []
    with Session(engine) as session:
        [event] = session.scalars(
            select(AuditLog).where(
                AuditLog.entity_type == "security", AuditLog.actor_id == str(kitchen.id)
            )
        ).all()
    assert (event.action, event.actor_role) == ("PERMISSION_DENIED", "KITCHEN")
    # Only who, what and where are logged; never the request body.
    assert event.after == {
        "permission": "manage_menu",
        "method": "PATCH",
        "path": f"/api/v1/admin/items/{thali.id}",
    }


def test_students_cannot_edit_items(db_client: TestClient, engine: Engine, thali: MenuItem) -> None:
    response = db_client.patch(
        _url(thali.id), json={"price_paise": 100}, headers=_auth(_user(engine, Role.STUDENT))
    )

    assert response.status_code == 403
    assert _stored(engine, thali).price_paise == 8000


def test_editing_requires_a_token(db_client: TestClient, engine: Engine, thali: MenuItem) -> None:
    assert db_client.patch(_url(thali.id), json={"price_paise": 100}).status_code == 401
    assert _stored(engine, thali).price_paise == 8000
