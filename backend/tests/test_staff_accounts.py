"""US-03 (FR-2, FR-3) acceptance tests TC-US03-AC1..AC3 through /api/v1/admin/users."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.enums import Role
from app.models.identity import User
from app.models.platform import AuditLog

URL = "/api/v1/admin/users"
PASSWORD = "kitchen-horse"


def _user(engine: Engine, role: Role, *, active: bool = True) -> User:
    user = User(
        id=uuid.uuid4(),
        name=f"{role.value.title()} user",
        email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
        password_hash="unused",
        role=role,
        is_active=active,
    )
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add(user)
    return user


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _as(user: User) -> dict[str, str]:
    return _bearer(create_access_token(user.id, user.role))


@pytest.fixture
def admin(engine: Engine) -> User:
    return _user(engine, Role.ADMIN)


def _create(
    client: TestClient, admin: User, *, email: str = "cook@caf.example", role: str = "KITCHEN"
) -> Any:
    return client.post(
        URL,
        json={"name": "Ravi", "email": email, "password": PASSWORD, "role": role},
        headers=_as(admin),
    )


def _login(client: TestClient, email: str, password: str = PASSWORD) -> Any:
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _audit(engine: Engine, user_id: str) -> list[AuditLog]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(AuditLog).where(AuditLog.entity_id == user_id).order_by(AuditLog.id)
            )
        )


@pytest.mark.parametrize("role", ["KITCHEN", "ADMIN"])
def test_tc_us03_ac1_a_created_staff_account_logs_in_with_its_role(
    db_client: TestClient, admin: User, role: str
) -> None:
    created = _create(db_client, admin, role=role)

    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["email"], body["role"], body["is_active"]) == ("cook@caf.example", role, True)
    assert "password" not in created.text
    logged_in = _login(db_client, "cook@caf.example")
    assert logged_in.status_code == 200
    # The client opens this role's dashboard (FR-5).
    assert logged_in.json()["role"] == role


def test_tc_us03_ac2_deactivation_stops_login_refresh_and_access_tokens_at_once(
    db_client: TestClient, admin: User
) -> None:
    staff_id = _create(db_client, admin).json()["id"]
    tokens = _login(db_client, "cook@caf.example").json()
    assert (
        db_client.get("/api/v1/auth/me", headers=_bearer(tokens["access_token"])).status_code == 200
    )

    response = db_client.post(f"{URL}/{staff_id}/deactivate", headers=_as(admin))

    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert _login(db_client, "cook@caf.example").status_code == 401
    refreshed = db_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refreshed.status_code == 401
    # Well within P-ACCESS_TTL: every request re-reads the account.
    me = db_client.get("/api/v1/auth/me", headers=_bearer(tokens["access_token"]))
    assert me.status_code == 401


def test_tc_us03_ac3_registering_with_role_admin_is_422_and_creates_nothing(
    db_client: TestClient, engine: Engine
) -> None:
    response = db_client.post(
        "/api/v1/auth/register",
        json={
            "name": "Mallory",
            "email": "mallory@iitk.ac.in",
            "password": "correct-horse",
            "role": "ADMIN",
        },
    )

    assert response.status_code == 422
    with Session(engine) as session:
        assert (
            session.scalars(select(User).where(User.email == "mallory@iitk.ac.in")).first() is None
        )


def test_a_reactivated_account_logs_in_again_but_old_refresh_tokens_stay_revoked(
    db_client: TestClient, admin: User
) -> None:
    staff_id = _create(db_client, admin).json()["id"]
    old = _login(db_client, "cook@caf.example").json()
    db_client.post(f"{URL}/{staff_id}/deactivate", headers=_as(admin))

    response = db_client.post(f"{URL}/{staff_id}/reactivate", headers=_as(admin))

    assert response.json()["is_active"] is True
    assert _login(db_client, "cook@caf.example").status_code == 200
    stale = db_client.post("/api/v1/auth/refresh", json={"refresh_token": old["refresh_token"]})
    assert stale.status_code == 401


def test_changes_are_audited_without_the_password(
    db_client: TestClient, engine: Engine, admin: User
) -> None:
    staff_id = _create(db_client, admin).json()["id"]
    db_client.post(f"{URL}/{staff_id}/deactivate", headers=_as(admin))
    # Repeating it changes nothing and writes nothing.
    db_client.post(f"{URL}/{staff_id}/deactivate", headers=_as(admin))
    db_client.post(f"{URL}/{staff_id}/reactivate", headers=_as(admin))

    rows = _audit(engine, staff_id)

    assert [row.action for row in rows] == [
        "ACCOUNT_CREATED",
        "ACCOUNT_DEACTIVATED",
        "ACCOUNT_REACTIVATED",
    ]
    assert all(row.actor_id == str(admin.id) and row.actor_role == "ADMIN" for row in rows)
    assert rows[1].before == {"is_active": True} and rows[1].after == {"is_active": False}
    assert PASSWORD not in str([(row.before, row.after) for row in rows])


def test_an_administrator_cannot_change_their_own_account(
    db_client: TestClient, admin: User
) -> None:
    for action in ("deactivate", "reactivate"):
        response = db_client.post(f"{URL}/{admin.id}/{action}", headers=_as(admin))
        assert response.status_code == 409


def test_any_other_account_can_be_deactivated_including_a_student(
    db_client: TestClient, engine: Engine, admin: User
) -> None:
    student = _user(engine, Role.STUDENT)

    response = db_client.post(f"{URL}/{student.id}/deactivate", headers=_as(admin))

    assert response.status_code == 200
    assert db_client.get("/api/v1/auth/me", headers=_as(student)).status_code == 401


def test_an_unknown_account_is_404(db_client: TestClient, admin: User) -> None:
    response = db_client.post(f"{URL}/{uuid.uuid4()}/deactivate", headers=_as(admin))

    assert response.status_code == 404


def test_students_are_not_created_here(db_client: TestClient, admin: User) -> None:
    assert _create(db_client, admin, role="STUDENT").status_code == 422


def test_a_duplicate_email_is_409(db_client: TestClient, admin: User) -> None:
    _create(db_client, admin)

    assert _create(db_client, admin, email="COOK@caf.example ").status_code == 409


@pytest.mark.parametrize(
    "body",
    [
        {"name": "R", "email": "not-an-email", "password": PASSWORD, "role": "KITCHEN"},
        {"name": "R", "email": "r@caf.example", "password": "short", "role": "KITCHEN"},
        {"name": "", "email": "r@caf.example", "password": PASSWORD, "role": "KITCHEN"},
        {"name": "R\u0000", "email": "r@caf.example", "password": PASSWORD, "role": "KITCHEN"},
        {"name": "R", "email": "r@caf.example", "password": PASSWORD, "role": "CHEF"},
        {"name": "R", "email": "r@caf.example", "password": PASSWORD, "role": "KITCHEN", "x": 1},
    ],
)
def test_invalid_accounts_are_422(db_client: TestClient, admin: User, body: dict[str, Any]) -> None:
    response = db_client.post(URL, json=body, headers=_as(admin))

    assert response.status_code == 422, response.text
    assert PASSWORD not in response.text


def test_the_list_shows_staff_accounts_but_no_students(
    db_client: TestClient, engine: Engine, admin: User
) -> None:
    _user(engine, Role.STUDENT)
    inactive = _user(engine, Role.KITCHEN, active=False)
    _create(db_client, admin)

    response = db_client.get(URL, headers=_as(admin))

    assert response.status_code == 200
    listed = {(row["email"], row["role"], row["is_active"]) for row in response.json()}
    assert listed == {
        (admin.email, "ADMIN", True),
        (inactive.email, "KITCHEN", False),
        ("cook@caf.example", "KITCHEN", True),
    }


@pytest.mark.parametrize("role", [Role.STUDENT, Role.KITCHEN])
def test_only_the_administrator_manages_accounts(
    db_client: TestClient, engine: Engine, admin: User, role: Role
) -> None:
    caller = _as(_user(engine, role))
    target = _user(engine, Role.KITCHEN)

    responses = [
        db_client.get(URL, headers=caller),
        db_client.post(
            URL,
            json={"name": "R", "email": "r@caf.example", "password": PASSWORD, "role": "ADMIN"},
            headers=caller,
        ),
        db_client.post(f"{URL}/{target.id}/deactivate", headers=caller),
        db_client.post(f"{URL}/{target.id}/reactivate", headers=caller),
    ]

    assert [response.status_code for response in responses] == [403] * 4
    assert db_client.get(URL).status_code == 401
