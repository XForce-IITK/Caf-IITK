"""CAFIITK-200: a NUL character in request text is a field-level 422, never a 500.

PostgreSQL cannot store or compare U+0000 in text, so before the fix a NUL in
these fields passed validation and failed inside the query (NFR-22).
"""

import uuid

from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.enums import Role
from app.models.identity import User


def _client(db_client: TestClient) -> TestClient:
    # A 500 must come back as a response, not be raised into the test.
    return TestClient(db_client.app, raise_server_exceptions=False)


def _admin_headers(engine: Engine) -> dict[str, str]:
    admin = User(
        id=uuid.uuid4(),
        name="Admin",
        email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
        password_hash="unused",
        role=Role.ADMIN,
    )
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add(admin)
    return {
        "Authorization": f"Bearer {create_access_token(admin.id, admin.role)}",
        "Idempotency-Key": uuid.uuid4().hex,
    }


def _rejects_nul(response: Response, field: str) -> None:
    assert response.status_code == 422, response.text
    [error] = response.json()["detail"]
    assert error["loc"][-1] == field
    assert "NUL" in error["msg"]


def test_a_nul_in_a_login_email_is_422(db_client: TestClient) -> None:
    response = _client(db_client).post(
        "/api/v1/auth/login", json={"email": "a\u0000@iitk.ac.in", "password": "x"}
    )

    _rejects_nul(response, "email")


def test_a_nul_in_a_login_password_is_just_a_failed_login(db_client: TestClient) -> None:
    # Passwords are only hashed, never queried, so a NUL there is harmless.
    response = _client(db_client).post(
        "/api/v1/auth/login", json={"email": "a@iitk.ac.in", "password": "pass\u0000word"}
    )

    assert response.status_code == 401


def test_a_nul_in_a_registration_is_422(db_client: TestClient) -> None:
    client = _client(db_client)

    name = client.post(
        "/api/v1/auth/register",
        json={"name": "A\u0000B", "email": "nul@iitk.ac.in", "password": "correct-horse"},
    )
    email = client.post(
        "/api/v1/auth/register",
        json={"name": "A", "email": "n\u0000ul@iitk.ac.in", "password": "correct-horse"},
    )

    _rejects_nul(name, "name")
    _rejects_nul(email, "email")


def test_a_nul_in_admin_and_kitchen_text_is_422(db_client: TestClient, engine: Engine) -> None:
    client = _client(db_client)
    admin = _admin_headers(engine)
    item = client.post(
        "/api/v1/admin/items",
        json={"name": "Dosa", "category": "MEAL", "price_paise": 4000},
        headers=admin,
    ).json()

    _rejects_nul(
        client.post(
            "/api/v1/admin/items",
            json={"name": "Do\u0000sa", "category": "MEAL", "price_paise": 4000},
            headers=admin,
        ),
        "name",
    )
    _rejects_nul(
        client.post(
            "/api/v1/admin/items",
            json={"name": "Idli", "description": "\u0000", "category": "MEAL", "price_paise": 4000},
            headers=admin,
        ),
        "description",
    )
    _rejects_nul(
        client.post(
            f"/api/v1/items/{item['id']}/flag", json={"reason": "gas\u0000"}, headers=admin
        ),
        "reason",
    )
    _rejects_nul(
        client.post(
            f"/api/v1/admin/proposals/{uuid.uuid4()}/reject",
            json={"reason": "no\u0000"},
            headers=admin,
        ),
        "reason",
    )
    _rejects_nul(
        client.post(
            f"/api/v1/admin/orders/{uuid.uuid4()}/cancel",
            json={"version": 1, "reason": "out of\u0000stock"},
            headers=admin,
        ),
        "reason",
    )


def test_a_nul_in_a_text_query_parameter_is_422(db_client: TestClient, engine: Engine) -> None:
    """CAFIITK-203: query parameters reach the same text comparisons as bodies."""
    client = _client(db_client)
    admin = _admin_headers(engine)
    probes = [
        ("/api/v1/admin/audit", name) for name in ("actor_id", "entity_type", "entity_id", "action")
    ] + [("/api/v1/admin/orders", "student"), ("/api/v1/admin/students", "search")]

    for path, name in probes:
        _rejects_nul(client.get(path, params={name: "a\u0000"}, headers=admin), name)


def test_absent_text_query_parameters_still_work(db_client: TestClient, engine: Engine) -> None:
    client = _client(db_client)
    admin = _admin_headers(engine)

    for path in ("/api/v1/admin/audit", "/api/v1/admin/orders", "/api/v1/admin/students"):
        assert client.get(path, headers=admin).status_code == 200, path
