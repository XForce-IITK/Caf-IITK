"""US-01 (FR-1) acceptance tests TC-US01-AC1..AC3, plus US-03 AC3, against real PostgreSQL."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.models.identity import User
from app.modules.identity.repository import UserRepository

URL = "/api/v1/auth/register"
BODY = {"name": "A Student", "email": "a@iitk.ac.in", "password": "12345678"}


def _users(engine: Engine) -> list[User]:
    with Session(engine) as session:
        return list(session.scalars(select(User)))


def test_tc_us01_ac1_registers_a_student(db_client: TestClient, engine: Engine) -> None:
    response = db_client.post(URL, json=BODY)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "a@iitk.ac.in"
    assert body["name"] == "A Student"
    assert body["role"] == "STUDENT"
    assert "password" not in body and "password_hash" not in body

    [user] = _users(engine)
    assert str(user.id) == body["id"]
    assert user.is_active
    # Login itself is US-02; here we check the stored credential will verify.
    assert verify_password(user.password_hash, "12345678")
    assert user.password_hash != "12345678"


def test_tc_us01_ac2_duplicate_email_gets_409(db_client: TestClient, engine: Engine) -> None:
    assert db_client.post(URL, json=BODY).status_code == 201

    response = db_client.post(URL, json={**BODY, "name": "Someone Else"})

    assert response.status_code == 409
    assert len(_users(engine)) == 1


def test_duplicate_email_differing_only_in_case_gets_409(
    db_client: TestClient, engine: Engine
) -> None:
    assert db_client.post(URL, json=BODY).status_code == 201

    response = db_client.post(URL, json={**BODY, "email": "A@IITK.AC.IN"})

    assert response.status_code == 409
    assert len(_users(engine)) == 1


def test_tc_us01_ac3_non_institute_email_gets_422(db_client: TestClient, engine: Engine) -> None:
    response = db_client.post(URL, json={**BODY, "email": "a@gmail.com"})

    assert response.status_code == 422
    assert _users(engine) == []


def test_us03_ac3_role_field_is_rejected(db_client: TestClient, engine: Engine) -> None:
    response = db_client.post(URL, json={**BODY, "role": "ADMIN"})

    assert response.status_code == 422
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(User)) == 0


def test_short_password_gets_422(db_client: TestClient, engine: Engine) -> None:
    response = db_client.post(URL, json={**BODY, "password": "1234567"})

    assert response.status_code == 422
    assert _users(engine) == []


def test_concurrent_duplicate_caught_by_unique_constraint_gets_409(
    db_client: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert db_client.post(URL, json=BODY).status_code == 201
    # Simulate a racing request that checked for the email before the first one committed.
    monkeypatch.setattr(UserRepository, "get_by_email", lambda self, email: None)

    response = db_client.post(URL, json=BODY)

    assert response.status_code == 409
    assert len(_users(engine)) == 1
