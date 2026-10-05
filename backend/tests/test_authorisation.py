"""US-04 (CAFIITK-129, FR-6) acceptance tests TC-US04-AC1..AC3.

The price-change (US-07, CAFIITK-132) and order-cancellation (US-28,
CAFIITK-153) endpoints are built in later sprints, so AC1 and AC2 use stand-in
routes guarded by the same permissions those endpoints must declare. Each of
those tickets adds its own endpoint-level 403 test; AC3 also gets one with the
slot-configuration endpoint (CAFIITK-139).
"""

import uuid
from collections.abc import Iterator
from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import create_access_token
from app.db.session import get_session
from app.models.enums import Role
from app.models.identity import User
from app.models.platform import AuditLog
from app.modules.identity.dependencies import require_permission
from app.modules.identity.permissions import Permission


@pytest.fixture
def handled() -> list[str]:
    """Names of the stand-in handlers that actually ran."""
    return []


@pytest.fixture
def guarded(engine: Engine, handled: list[str]) -> Iterator[TestClient]:
    app = FastAPI()

    @app.patch("/admin/items/{item_id}/price")
    def change_price(
        item_id: str, user: Annotated[User, Depends(require_permission(Permission.MANAGE_MENU))]
    ) -> dict[str, str]:
        handled.append("change_price")
        return {"item_id": item_id}

    @app.post("/admin/orders/{order_id}/cancel")
    def cancel_order(
        order_id: str,
        user: Annotated[User, Depends(require_permission(Permission.CANCEL_ANY_ORDER))],
    ) -> dict[str, str]:
        handled.append("cancel_order")
        return {"order_id": order_id}

    @app.put("/admin/service-days/{day}")
    def configure_slots(
        day: str, user: Annotated[User, Depends(require_permission(Permission.MANAGE_CAPACITY))]
    ) -> dict[str, str]:
        handled.append("configure_slots")
        return {"day": day}

    @app.put("/admin/inventory/{day}/{item_id}")
    def set_inventory(
        day: str,
        item_id: str,
        user: Annotated[User, Depends(require_permission(Permission.MANAGE_CAPACITY))],
    ) -> dict[str, str]:
        handled.append("set_inventory")
        return {"day": day}

    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def test_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    yield TestClient(app)
    with engine.begin() as connection:
        connection.execute(delete(AuditLog))
        connection.execute(delete(User))


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


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


def _security_events(engine: Engine, user: User) -> list[dict[str, Any]]:
    with Session(engine) as session:
        rows = session.scalars(
            select(AuditLog).where(
                AuditLog.entity_type == "security", AuditLog.actor_id == str(user.id)
            )
        ).all()
        return [{"action": r.action, "actor_role": r.actor_role, "after": r.after} for r in rows]


def test_tc_us04_ac1_kitchen_cannot_change_a_price_and_it_is_logged(
    guarded: TestClient, engine: Engine, handled: list[str]
) -> None:
    kitchen = _user(engine, Role.KITCHEN)

    response = guarded.patch(
        "/admin/items/thali/price", json={"price_paise": 1}, headers=_auth(kitchen)
    )

    assert response.status_code == 403
    assert handled == []  # the handler never ran, so the price is unchanged
    assert _security_events(engine, kitchen) == [
        {
            "action": "PERMISSION_DENIED",
            "actor_role": "KITCHEN",
            # Only who, what and where are logged; never the request body.
            "after": {
                "permission": "manage_menu",
                "method": "PATCH",
                "path": "/admin/items/thali/price",
            },
        }
    ]


def test_tc_us04_ac2_kitchen_cannot_cancel_a_students_order(
    guarded: TestClient, engine: Engine, handled: list[str]
) -> None:
    kitchen = _user(engine, Role.KITCHEN)

    response = guarded.post("/admin/orders/o-1/cancel", headers=_auth(kitchen))

    assert response.status_code == 403
    assert handled == []  # the order is unchanged
    assert [e["action"] for e in _security_events(engine, kitchen)] == ["PERMISSION_DENIED"]


@pytest.mark.parametrize(
    ("method", "path"),
    [("put", "/admin/inventory/2026-10-06/thali"), ("put", "/admin/service-days/2026-10-06")],
)
def test_tc_us04_ac3_student_cannot_touch_inventory_or_slot_configuration(
    guarded: TestClient, engine: Engine, handled: list[str], method: str, path: str
) -> None:
    student = _user(engine, Role.STUDENT)

    response = guarded.request(method.upper(), path, headers=_auth(student))

    assert response.status_code == 403
    assert handled == []


def test_admin_passes_every_admin_check(
    guarded: TestClient, engine: Engine, handled: list[str]
) -> None:
    admin = _user(engine, Role.ADMIN)
    headers = _auth(admin)

    assert guarded.patch("/admin/items/thali/price", headers=headers).status_code == 200
    assert guarded.post("/admin/orders/o-1/cancel", headers=headers).status_code == 200
    assert guarded.put("/admin/service-days/2026-10-06", headers=headers).status_code == 200
    assert handled == ["change_price", "cancel_order", "configure_slots"]
    assert _security_events(engine, admin) == []


def test_role_change_applies_immediately_without_a_new_token(
    guarded: TestClient, engine: Engine
) -> None:
    # Decision 1a: the role comes from the database, not from the token.
    user = _user(engine, Role.ADMIN)
    headers = _auth(user)
    assert guarded.patch("/admin/items/thali/price", headers=headers).status_code == 200

    with Session(engine) as session, session.begin():
        session.execute(update(User).where(User.id == user.id).values(role=Role.KITCHEN))

    assert guarded.patch("/admin/items/thali/price", headers=headers).status_code == 403


def test_missing_token_is_401_and_not_logged_as_a_permission_denial(
    guarded: TestClient, engine: Engine, handled: list[str]
) -> None:
    response = guarded.patch("/admin/items/thali/price")

    assert response.status_code == 401
    assert handled == []
    with Session(engine) as session:
        assert session.scalars(select(AuditLog)).all() == []
