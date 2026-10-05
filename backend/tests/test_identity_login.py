"""US-02 (FR-4, FR-5, NFR-19) acceptance tests TC-US02-AC1..AC4, plus refresh rotation."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.models.enums import Role
from app.models.identity import RefreshToken, User

PASSWORD = "correct-horse"


def _add_user(engine: Engine, email: str, role: Role, *, active: bool = True) -> User:
    with Session(engine, expire_on_commit=False) as session, session.begin():
        user = User(
            name=f"{role.value} user",
            email=email,
            password_hash=hash_password(PASSWORD),
            role=role,
            is_active=active,
        )
        session.add(user)
    return user


def _login(client: TestClient, email: str, password: str = PASSWORD) -> dict[str, Any]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("role", [Role.STUDENT, Role.KITCHEN, Role.ADMIN])
def test_tc_us02_ac1_each_role_logs_in_and_gets_its_role(
    db_client: TestClient, engine: Engine, role: Role
) -> None:
    email = f"{role.value.lower()}@iitk.ac.in"
    _add_user(engine, email, role)

    tokens = _login(db_client, email)

    assert tokens["role"] == role.value  # the client opens this role's dashboard (FR-5)
    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in"] == get_settings().access_ttl_min * 60
    me = db_client.get("/api/v1/auth/me", headers=_bearer(tokens["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == email
    assert me.json()["role"] == role.value


def test_registered_student_can_log_in(db_client: TestClient) -> None:
    """Closes US-01 AC1: a registered Student can log in."""
    body = {"name": "A Student", "email": "a@iitk.ac.in", "password": "12345678"}
    assert db_client.post("/api/v1/auth/register", json=body).status_code == 201

    assert _login(db_client, "A@iitk.ac.in", "12345678")["role"] == "STUDENT"


def test_tc_us02_ac2_wrong_password_gets_generic_401(db_client: TestClient, engine: Engine) -> None:
    _add_user(engine, "a@iitk.ac.in", Role.STUDENT)

    wrong_password = db_client.post(
        "/api/v1/auth/login", json={"email": "a@iitk.ac.in", "password": "wrong-horse"}
    )
    unknown_email = db_client.post(
        "/api/v1/auth/login", json={"email": "nobody@iitk.ac.in", "password": PASSWORD}
    )

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    # Same message either way, so it does not reveal which field was wrong.
    assert wrong_password.json() == unknown_email.json() == {"detail": "Invalid email or password"}


def test_deactivated_account_cannot_log_in(db_client: TestClient, engine: Engine) -> None:
    _add_user(engine, "gone@iitk.ac.in", Role.KITCHEN, active=False)

    response = db_client.post(
        "/api/v1/auth/login", json={"email": "gone@iitk.ac.in", "password": PASSWORD}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}


def test_tc_us02_ac3_refresh_token_is_rejected_after_logout(
    db_client: TestClient, engine: Engine
) -> None:
    _add_user(engine, "a@iitk.ac.in", Role.STUDENT)
    tokens = _login(db_client, "a@iitk.ac.in")

    logout = db_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers=_bearer(tokens["access_token"]),
    )
    refresh = db_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    assert logout.status_code == 204
    assert refresh.status_code == 401


def test_tc_us02_ac4_expired_access_token_gets_401(db_client: TestClient, engine: Engine) -> None:
    user = _add_user(engine, "a@iitk.ac.in", Role.STUDENT)
    issued = datetime.now(UTC) - timedelta(minutes=get_settings().access_ttl_min, seconds=1)
    expired = create_access_token(user.id, user.role, now=issued)

    response = db_client.get("/api/v1/auth/me", headers=_bearer(expired))

    assert response.status_code == 401


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer not-a-jwt"}])
def test_protected_endpoint_without_valid_token_gets_401(
    db_client: TestClient, headers: dict[str, str]
) -> None:
    assert db_client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_access_token_of_deactivated_user_is_refused(db_client: TestClient, engine: Engine) -> None:
    user = _add_user(engine, "a@iitk.ac.in", Role.STUDENT)
    tokens = _login(db_client, "a@iitk.ac.in")
    with engine.begin() as connection:
        connection.execute(update(User).where(User.id == user.id).values(is_active=False))

    me = db_client.get("/api/v1/auth/me", headers=_bearer(tokens["access_token"]))
    refresh = db_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    assert me.status_code == 401
    assert refresh.status_code == 401


def test_refresh_rotates_the_token(db_client: TestClient, engine: Engine) -> None:
    _add_user(engine, "a@iitk.ac.in", Role.STUDENT)
    first = _login(db_client, "a@iitk.ac.in")

    response = db_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )

    assert response.status_code == 200
    second = response.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert (
        db_client.get("/api/v1/auth/me", headers=_bearer(second["access_token"])).status_code == 200
    )
    # The new refresh token works once more.
    again = db_client.post("/api/v1/auth/refresh", json={"refresh_token": second["refresh_token"]})
    assert again.status_code == 200


def test_reusing_a_rotated_refresh_token_revokes_all_of_the_users_tokens(
    db_client: TestClient, engine: Engine
) -> None:
    _add_user(engine, "a@iitk.ac.in", Role.STUDENT)
    first = _login(db_client, "a@iitk.ac.in")
    second = db_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
    ).json()

    replay = db_client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    after = db_client.post("/api/v1/auth/refresh", json={"refresh_token": second["refresh_token"]})

    assert replay.status_code == 401
    assert after.status_code == 401  # the legitimate holder must log in again
    with Session(engine) as session:
        assert all(t.revoked_at is not None for t in session.scalars(select(RefreshToken)))


def test_expired_refresh_token_gets_401(db_client: TestClient, engine: Engine) -> None:
    _add_user(engine, "a@iitk.ac.in", Role.STUDENT)
    tokens = _login(db_client, "a@iitk.ac.in")
    with engine.begin() as connection:
        connection.execute(
            update(RefreshToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )

    response = db_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    assert response.status_code == 401


def test_unknown_refresh_token_gets_401(db_client: TestClient) -> None:
    response = db_client.post("/api/v1/auth/refresh", json={"refresh_token": "made-up"})
    assert response.status_code == 401


def test_logout_requires_an_access_token(db_client: TestClient) -> None:
    response = db_client.post("/api/v1/auth/logout", json={"refresh_token": "anything"})
    assert response.status_code == 401


def test_logout_cannot_revoke_another_users_token(db_client: TestClient, engine: Engine) -> None:
    _add_user(engine, "a@iitk.ac.in", Role.STUDENT)
    _add_user(engine, "b@iitk.ac.in", Role.STUDENT)
    alice, bob = _login(db_client, "a@iitk.ac.in"), _login(db_client, "b@iitk.ac.in")

    response = db_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": bob["refresh_token"]},
        headers=_bearer(alice["access_token"]),
    )

    assert response.status_code == 204
    refresh = db_client.post("/api/v1/auth/refresh", json={"refresh_token": bob["refresh_token"]})
    assert refresh.status_code == 200


def test_refresh_token_is_stored_only_as_a_hash(db_client: TestClient, engine: Engine) -> None:
    _add_user(engine, "a@iitk.ac.in", Role.STUDENT)
    tokens = _login(db_client, "a@iitk.ac.in")

    with Session(engine) as session:
        stored = session.scalars(select(RefreshToken.token_hash)).all()
    assert tokens["refresh_token"] not in stored


def test_login_rejects_unknown_fields(db_client: TestClient) -> None:
    response = db_client.post(
        "/api/v1/auth/login",
        json={"email": "a@iitk.ac.in", "password": PASSWORD, "role": "ADMIN"},
    )
    assert response.status_code == 422
