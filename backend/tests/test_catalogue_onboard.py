"""US-06 (CAFIITK-131, FR-8) acceptance tests TC-US06-AC1..AC3 via POST /api/v1/admin/items."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.catalogue import MenuItem
from app.models.enums import ItemStatus, Role
from app.models.identity import User
from app.models.platform import AuditLog
from app.modules.catalogue.repository import MenuItemRepository

URL = "/api/v1/admin/items"
THALI = {"name": "Paneer Thali", "category": "MEAL", "price_paise": 8000}


def _user(engine: Engine, role: Role) -> User:
    with Session(engine, expire_on_commit=False) as session, session.begin():
        user = User(
            id=uuid.uuid4(),
            name=f"{role.value} user",
            email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
            password_hash="unused",
            role=role,
        )
        session.add(user)
    return user


@pytest.fixture
def admin(engine: Engine) -> dict[str, str]:
    user = _user(engine, Role.ADMIN)
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


def _items(engine: Engine) -> list[MenuItem]:
    with Session(engine) as session:
        return list(session.scalars(select(MenuItem)).all())


def test_tc_us06_ac1_new_item_is_active(
    db_client: TestClient, engine: Engine, admin: dict[str, str]
) -> None:
    response = db_client.post(URL, json=THALI, headers=admin)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Paneer Thali"
    assert body["category"] == "MEAL"
    assert body["price_paise"] == 8000
    assert body["status"] == "ACTIVE"
    assert body["unavailable"] is False
    assert body["description"] == ""
    [stored] = _items(engine)
    assert str(stored.id) == body["id"]
    assert stored.status is ItemStatus.ACTIVE


def test_onboarding_is_audited_in_the_same_change(
    db_client: TestClient, engine: Engine, admin: dict[str, str]
) -> None:
    item_id = db_client.post(URL, json=THALI, headers=admin).json()["id"]

    with Session(engine) as session:
        [entry] = session.scalars(select(AuditLog).where(AuditLog.entity_id == item_id)).all()
    assert entry.action == "ITEM_CREATED"
    assert entry.actor_role == "ADMIN"
    assert entry.after == {
        "name": "Paneer Thali",
        "category": "MEAL",
        "price_paise": 8000,
        "status": "ACTIVE",
    }


@pytest.mark.parametrize("name", ["Paneer Thali", "paneer thali", "  PANEER THALI  "])
def test_tc_us06_ac2_duplicate_active_name_is_422(
    db_client: TestClient, engine: Engine, admin: dict[str, str], name: str
) -> None:
    assert db_client.post(URL, json=THALI, headers=admin).status_code == 201

    response = db_client.post(URL, json=THALI | {"name": name}, headers=admin)

    assert response.status_code == 422
    assert "already exists" in response.text
    assert len(_items(engine)) == 1


def test_name_of_a_removed_item_can_be_reused(
    db_client: TestClient, engine: Engine, admin: dict[str, str]
) -> None:
    first = db_client.post(URL, json=THALI, headers=admin).json()["id"]
    with Session(engine) as session, session.begin():
        session.execute(
            update(MenuItem).where(MenuItem.id == first).values(status=ItemStatus.REMOVED)
        )

    assert db_client.post(URL, json=THALI, headers=admin).status_code == 201


def test_concurrent_duplicate_caught_by_the_unique_index_is_422(
    db_client: TestClient, engine: Engine, admin: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert db_client.post(URL, json=THALI, headers=admin).status_code == 201
    # Simulate a racing request that checked the name before the first one committed.
    monkeypatch.setattr(MenuItemRepository, "active_name_exists", lambda self, name: False)

    response = db_client.post(URL, json=THALI, headers=admin)

    assert response.status_code == 422
    assert len(_items(engine)) == 1


@pytest.mark.parametrize("price_paise", [0, 99, 50_001, 50_100])
def test_tc_us06_ac3_price_outside_rs1_to_rs500_is_422(
    db_client: TestClient, engine: Engine, admin: dict[str, str], price_paise: int
) -> None:
    response = db_client.post(URL, json=THALI | {"price_paise": price_paise}, headers=admin)

    assert response.status_code == 422
    assert _items(engine) == []


@pytest.mark.parametrize("price_paise", [100, 50_000])
def test_price_boundaries_are_accepted(
    db_client: TestClient, admin: dict[str, str], price_paise: int
) -> None:
    response = db_client.post(URL, json=THALI | {"price_paise": price_paise}, headers=admin)
    assert response.status_code == 201


@pytest.mark.parametrize(
    "change",
    [
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 61},
        {"description": "x" * 301},
        {"category": "DRINK"},
        {"status": "REMOVED"},  # unknown field: new items are always ACTIVE
    ],
)
def test_invalid_input_is_422(
    db_client: TestClient, engine: Engine, admin: dict[str, str], change: dict[str, Any]
) -> None:
    response = db_client.post(URL, json=THALI | change, headers=admin)

    assert response.status_code == 422
    assert _items(engine) == []


def test_limits_are_accepted(db_client: TestClient, admin: dict[str, str]) -> None:
    body = THALI | {"name": "x" * 60, "description": "y" * 300, "category": "DESSERT"}
    assert db_client.post(URL, json=body, headers=admin).status_code == 201


@pytest.mark.parametrize("role", [Role.KITCHEN, Role.STUDENT])
def test_only_the_administrator_can_onboard(
    db_client: TestClient, engine: Engine, role: Role
) -> None:
    user = _user(engine, role)
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}

    response = db_client.post(URL, json=THALI, headers=headers)

    assert response.status_code == 403
    assert _items(engine) == []


def test_onboarding_requires_a_token(db_client: TestClient, engine: Engine) -> None:
    assert db_client.post(URL, json=THALI).status_code == 401
    assert _items(engine) == []
