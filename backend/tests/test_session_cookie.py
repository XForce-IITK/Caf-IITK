"""CAFIITK-207: the web client's refresh token travels in an HttpOnly cookie.

A reload keeps the user logged in (the client restores the session with one
refresh), while page scripts can never read the refresh token.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.main import create_app
from app.models.enums import Role
from app.models.identity import User
from app.modules.identity.cookie import REFRESH_COOKIE

EMAIL = "asha@iitk.ac.in"
PASSWORD = "correct-horse"
COOKIE_MODE = {"X-Token-Transport": "cookie"}
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"


@pytest.fixture
def client(db_client: TestClient, engine: Engine) -> TestClient:
    """The API client, with one Student account."""
    with Session(engine) as session, session.begin():
        session.add(
            User(
                name="Asha",
                email=EMAIL,
                password_hash=hash_password(PASSWORD),
                role=Role.STUDENT,
            )
        )
    return db_client


def _cookie_login(client: TestClient) -> dict[str, Any]:
    response = client.post(LOGIN, json={"email": EMAIL, "password": PASSWORD}, headers=COOKIE_MODE)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _set_cookie(response: Any) -> str:
    header: str = response.headers["set-cookie"]
    return header


def test_cookie_login_keeps_the_refresh_token_out_of_the_body(client: TestClient) -> None:
    response = client.post(LOGIN, json={"email": EMAIL, "password": PASSWORD}, headers=COOKIE_MODE)

    assert response.status_code == 200
    assert response.json()["refresh_token"] is None
    assert response.json()["access_token"]
    cookie = _set_cookie(response).lower()
    assert cookie.startswith(f"{REFRESH_COOKIE}=")
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/api/v1/auth" in cookie
    assert f"max-age={get_settings().refresh_ttl_days * 24 * 3600}" in cookie


def test_a_reload_restores_the_session_from_the_cookie(client: TestClient) -> None:
    _cookie_login(client)
    first = client.cookies[REFRESH_COOKIE]

    # After a reload the client has nothing in memory: an empty body, the cookie only.
    response = client.post(REFRESH, json={}, headers=COOKIE_MODE)

    assert response.status_code == 200, response.text
    assert response.json()["refresh_token"] is None
    assert response.json()["role"] == "STUDENT"
    me = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {response.json()['access_token']}"}
    )
    assert me.json()["email"] == EMAIL
    # Rotated (NFR-19): a new cookie, and the old token is no longer accepted.
    assert client.cookies[REFRESH_COOKIE] != first
    replay = client.post(REFRESH, json={"refresh_token": first})
    assert replay.status_code == 401


def test_the_cookie_is_ignored_without_the_transport_header(client: TestClient) -> None:
    """CSRF guard: a cross-site form cannot add the header without a CORS preflight."""
    _cookie_login(client)

    response = client.post(REFRESH, json={})

    assert response.status_code == 422


def test_a_failed_refresh_removes_the_cookie(client: TestClient) -> None:
    client.cookies.set(REFRESH_COOKIE, "not-a-real-token", path="/api/v1/auth")

    response = client.post(REFRESH, json={}, headers=COOKIE_MODE)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid refresh token"}
    assert _set_cookie(response).startswith(f'{REFRESH_COOKIE}=""')
    assert "max-age=0" in _set_cookie(response).lower()


def test_logout_revokes_the_cookie_token_and_clears_it(client: TestClient) -> None:
    tokens = _cookie_login(client)
    token = client.cookies[REFRESH_COOKIE]

    response = client.post(
        LOGOUT,
        json={},
        headers={**COOKIE_MODE, "Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 204
    assert "max-age=0" in _set_cookie(response).lower()
    assert client.post(REFRESH, json={"refresh_token": token}).status_code == 401


def test_clients_without_the_header_still_get_the_token_in_the_body(
    client: TestClient,
) -> None:
    """The Android app keeps its refresh token in secure storage itself."""
    response = client.post(LOGIN, json={"email": EMAIL, "password": PASSWORD})

    assert response.json()["refresh_token"]
    assert "set-cookie" not in response.headers
    rotated = client.post(REFRESH, json={"refresh_token": response.json()["refresh_token"]})
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"]


def test_refresh_without_any_token_is_422(client: TestClient) -> None:
    """A first visit has no cookie yet; the client treats this as logged out."""
    assert client.post(REFRESH, json={}).status_code == 422
    assert client.post(REFRESH, json={}, headers=COOKIE_MODE).status_code == 422


def test_the_cookie_is_secure_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.identity.cookie import cleared_headers

    monkeypatch.setenv("CAF_ENV", "production")
    monkeypatch.setenv("CAF_JWT_SECRET", "p" * 40)
    get_settings.cache_clear()
    try:
        assert "secure" in cleared_headers()["set-cookie"].lower()
    finally:
        get_settings.cache_clear()


def test_the_browser_may_send_the_cookie_and_the_header_from_the_client_origin() -> None:
    client = TestClient(create_app())
    response = client.options(
        REFRESH,
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-token-transport",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "x-token-transport" in response.headers["access-control-allow-headers"].lower()
