"""US-11 (CAFIITK-136, FR-14) acceptance test TC-US11-AC1, plus the FR-15 guard (US-12 AC1/AC2),
via PUT /api/v1/admin/inventory/{date}/{item}."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.capacity import DailyInventory, ServiceDay
from app.models.catalogue import MenuItem
from app.models.enums import ItemCategory, ItemStatus, Role
from app.models.identity import User
from app.models.platform import AuditLog

D = date(2026, 10, 20)


def _url(item_id: uuid.UUID | str, service_date: date | str = D) -> str:
    return f"/api/v1/admin/inventory/{service_date}/{item_id}"


def _headers(engine: Engine, role: Role) -> dict[str, str]:
    with Session(engine, expire_on_commit=False) as session, session.begin():
        user = User(
            id=uuid.uuid4(),
            name=f"{role.value} user",
            email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
            password_hash="unused",
            role=role,
        )
        session.add(user)
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


@pytest.fixture
def admin(engine: Engine) -> dict[str, str]:
    return _headers(engine, Role.ADMIN)


@pytest.fixture
def thali(engine: Engine) -> uuid.UUID:
    """An ACTIVE item and a configured service day D."""
    with Session(engine, expire_on_commit=False) as session, session.begin():
        item = MenuItem(name="Thali", category=ItemCategory.MEAL, price_paise=8000)
        session.add(item)
        session.add(
            ServiceDay(
                service_date=D,
                window_start=time(12, 0),
                window_end=time(14, 0),
                slot_len_min=15,
                default_capacity=30,
            )
        )
    return item.id


def _put(client: TestClient, item_id: uuid.UUID, total: Any, headers: dict[str, str]) -> Any:
    return client.put(_url(item_id), json={"total": total}, headers=headers)


def _row(engine: Engine, item_id: uuid.UUID) -> DailyInventory | None:
    with Session(engine) as session:
        return session.get(DailyInventory, (item_id, D))


def _audits(engine: Engine, item_id: uuid.UUID) -> list[AuditLog]:
    """INVENTORY_SET entries for this item; audit_log is append-only, so scope by entity."""
    with Session(engine) as session:
        return list(
            session.scalars(
                select(AuditLog)
                .where(
                    AuditLog.action == "INVENTORY_SET",
                    AuditLog.entity_id == f"{item_id}:{D.isoformat()}",
                )
                .order_by(AuditLog.id)
            )
        )


def _set_allocated(engine: Engine, item_id: uuid.UUID, allocated: int) -> None:
    with engine.begin() as connection:
        connection.execute(
            update(DailyInventory)
            .where(DailyInventory.item_id == item_id, DailyInventory.service_date == D)
            .values(allocated=allocated)
        )


def test_tc_us11_ac1_set_50_portions(
    db_client: TestClient, engine: Engine, admin: dict[str, str], thali: uuid.UUID
) -> None:
    response = _put(db_client, thali, 50, admin)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "item_id": str(thali),
        "service_date": "2026-10-20",
        "total": 50,
        "allocated": 0,
        "available": 50,
    }
    row = _row(engine, thali)
    assert row is not None and (row.total, row.allocated) == (50, 0)


def test_setting_again_replaces_the_total(
    db_client: TestClient, engine: Engine, admin: dict[str, str], thali: uuid.UUID
) -> None:
    _put(db_client, thali, 50, admin)

    response = _put(db_client, thali, 20, admin)

    assert response.status_code == 200
    assert response.json()["available"] == 20
    with Session(engine) as session:
        assert len(session.scalars(select(DailyInventory)).all()) == 1


def test_us12_ac1_reducing_below_allocated_gets_409_and_changes_nothing(
    db_client: TestClient, engine: Engine, admin: dict[str, str], thali: uuid.UUID
) -> None:
    _put(db_client, thali, 50, admin)
    _set_allocated(engine, thali, 30)

    response = _put(db_client, thali, 25, admin)

    assert response.status_code == 409
    assert "30" in response.json()["detail"]
    row = _row(engine, thali)
    assert row is not None and (row.total, row.allocated) == (50, 30)


def test_us12_ac2_replenishing_increases_available(
    db_client: TestClient, engine: Engine, admin: dict[str, str], thali: uuid.UUID
) -> None:
    _put(db_client, thali, 50, admin)
    _set_allocated(engine, thali, 30)

    response = _put(db_client, thali, 70, admin)

    assert response.status_code == 200
    assert response.json()["available"] == 40


def test_reducing_exactly_to_allocated_is_allowed(
    db_client: TestClient, engine: Engine, admin: dict[str, str], thali: uuid.UUID
) -> None:
    _put(db_client, thali, 50, admin)
    _set_allocated(engine, thali, 30)

    response = _put(db_client, thali, 30, admin)

    assert response.status_code == 200
    assert response.json()["available"] == 0


@pytest.mark.parametrize("total", [-1, 501, 2.5, "fifty", None])
def test_total_outside_0_to_500_gets_422(
    db_client: TestClient, engine: Engine, admin: dict[str, str], thali: uuid.UUID, total: Any
) -> None:
    assert _put(db_client, thali, total, admin).status_code == 422
    assert _row(engine, thali) is None


@pytest.mark.parametrize("total", [0, 500])
def test_bounds_are_accepted(
    db_client: TestClient, admin: dict[str, str], thali: uuid.UUID, total: int
) -> None:
    assert _put(db_client, thali, total, admin).status_code == 200


def test_unknown_field_gets_422(
    db_client: TestClient, admin: dict[str, str], thali: uuid.UUID
) -> None:
    response = db_client.put(_url(thali), json={"total": 5, "allocated": 0}, headers=admin)
    assert response.status_code == 422


def test_unknown_item_gets_404(
    db_client: TestClient, admin: dict[str, str], thali: uuid.UUID
) -> None:
    assert _put(db_client, uuid.uuid4(), 10, admin).status_code == 404


def test_removed_item_gets_409(
    db_client: TestClient, engine: Engine, admin: dict[str, str], thali: uuid.UUID
) -> None:
    with engine.begin() as connection:
        connection.execute(
            update(MenuItem).where(MenuItem.id == thali).values(status=ItemStatus.REMOVED)
        )

    response = _put(db_client, thali, 10, admin)

    assert response.status_code == 409
    assert _row(engine, thali) is None


def test_unconfigured_service_date_gets_409(
    db_client: TestClient, engine: Engine, admin: dict[str, str], thali: uuid.UUID
) -> None:
    response = db_client.put(_url(thali, "2026-10-21"), json={"total": 10}, headers=admin)

    assert response.status_code == 409
    assert response.json()["detail"] == "Service date is not configured"


def test_malformed_date_or_item_gets_422(
    db_client: TestClient, admin: dict[str, str], thali: uuid.UUID
) -> None:
    assert (
        db_client.put(_url(thali, "20-10-2026"), json={"total": 1}, headers=admin).status_code
        == 422
    )
    assert db_client.put(_url("not-a-uuid"), json={"total": 1}, headers=admin).status_code == 422


@pytest.mark.parametrize("role", [Role.STUDENT, Role.KITCHEN])
def test_non_admin_gets_403(
    db_client: TestClient, engine: Engine, thali: uuid.UUID, role: Role
) -> None:
    response = _put(db_client, thali, 10, _headers(engine, role))

    assert response.status_code == 403
    assert _row(engine, thali) is None


def test_anonymous_gets_401(db_client: TestClient, thali: uuid.UUID) -> None:
    assert _put(db_client, thali, 10, {}).status_code == 401


def test_each_change_is_audited_with_before_and_after(
    db_client: TestClient, engine: Engine, admin: dict[str, str], thali: uuid.UUID
) -> None:
    _put(db_client, thali, 50, admin)
    _put(db_client, thali, 60, admin)

    entries = _audits(engine, thali)
    assert [(e.before, e.after) for e in entries] == [
        (None, {"total": 50, "allocated": 0}),
        ({"total": 50, "allocated": 0}, {"total": 60, "allocated": 0}),
    ]
    assert entries[0].entity_type == "daily_inventory"
    assert entries[0].entity_id == f"{thali}:2026-10-20"
    assert entries[0].actor_role == "ADMIN"


def test_rejected_change_is_not_audited(
    db_client: TestClient, engine: Engine, admin: dict[str, str], thali: uuid.UUID
) -> None:
    _put(db_client, thali, 50, admin)
    _set_allocated(engine, thali, 30)
    _put(db_client, thali, 10, admin)

    assert len(_audits(engine, thali)) == 1


def test_concurrent_first_sets_create_one_row(
    db_client: TestClient, engine: Engine, admin: dict[str, str], thali: uuid.UUID
) -> None:
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda t: _put(db_client, thali, t, admin), range(10, 18)))

    assert all(r.status_code == 200 for r in responses)
    with Session(engine) as session:
        [row] = session.scalars(select(DailyInventory)).all()
        assert row.total in range(10, 18)
    entries = _audits(engine, thali)
    assert len(entries) == 8
    # Exactly one of the eight saw no previous row.
    assert sum(e.before is None for e in entries) == 1


def test_check_constraint_refuses_allocated_above_total(
    engine: Engine, db_client: TestClient, admin: dict[str, str], thali: uuid.UUID
) -> None:
    """Last line of defence (NFR-2): even a direct write cannot oversell."""
    _put(db_client, thali, 5, admin)
    with pytest.raises(IntegrityError):
        _set_allocated(engine, thali, 6)
