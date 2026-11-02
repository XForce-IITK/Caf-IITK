"""NFR-20 and NFR-21: password handling and rate limits with shared counters.

The cross-process test sends real HTTP to two caf-api processes (`live_stack`), so
it checks that the limit holds however many API workers run (NFR-13).
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from conftest import LiveStack
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app.core import clock
from app.core.security import create_access_token, hash_password
from app.models.enums import Role
from app.models.identity import User
from app.models.platform import RateLimit
from app.modules.identity.rate_limit import RateLimiter

PASSWORD = "correct-horse"
LOGIN = "/api/v1/auth/login"


def _add_user(engine: Engine, email: str, role: Role = Role.STUDENT) -> User:
    with Session(engine, expire_on_commit=False) as session, session.begin():
        user = User(name="User", email=email, password_hash=hash_password(PASSWORD), role=role)
        session.add(user)
    return user


def _login(client: TestClient, email: str, password: str) -> httpx.Response:
    response: httpx.Response = client.post(LOGIN, json={"email": email, "password": password})
    return response


def _from(client: TestClient, ip: str) -> TestClient:
    """The same app, seen from another client address."""
    return TestClient(client.app, client=(ip, 50000))


class Clock:
    def __init__(self) -> None:
        self.at = datetime(2026, 11, 3, 12, 0, 10, tzinfo=clock.IST)

    def __call__(self) -> datetime:
        return self.at


@pytest.fixture
def now(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(clock, "now", fake)
    return fake


def test_nfr21_sixth_failed_login_for_an_account_gets_429(
    db_client: TestClient, engine: Engine, now: Clock
) -> None:
    _add_user(engine, "victim@iitk.ac.in")
    for _ in range(5):
        assert _login(db_client, "victim@iitk.ac.in", "guess").status_code == 401

    # Even the right password is refused until the window ends: the password is not checked.
    refused = _login(db_client, "victim@iitk.ac.in", PASSWORD)

    assert refused.status_code == 429
    assert refused.headers["Retry-After"] == "50"
    # The client shows this detail as it is.
    assert refused.json()["detail"] == "Too many attempts. Try again in 50 seconds."
    assert PASSWORD not in refused.text


def test_nfr21_account_limit_holds_across_client_addresses(
    db_client: TestClient, engine: Engine, now: Clock
) -> None:
    _add_user(engine, "victim@iitk.ac.in")
    for n in range(5):
        attacker = _from(db_client, f"10.0.0.{n}")
        assert _login(attacker, "victim@iitk.ac.in", "guess").status_code == 401

    assert _login(_from(db_client, "10.0.0.9"), "victim@iitk.ac.in", "guess").status_code == 429


def test_nfr21_address_limit_holds_across_accounts(
    db_client: TestClient, engine: Engine, now: Clock
) -> None:
    # Spraying one password over many accounts, including ones that do not exist.
    for n in range(5):
        assert _login(db_client, f"user{n}@iitk.ac.in", "guess").status_code == 401

    assert _login(db_client, "user9@iitk.ac.in", "guess").status_code == 429
    # Another address is not affected.
    _add_user(engine, "other@iitk.ac.in")
    assert _login(_from(db_client, "10.0.0.7"), "other@iitk.ac.in", PASSWORD).status_code == 200


def test_nfr21_successful_logins_do_not_count(
    db_client: TestClient, engine: Engine, now: Clock
) -> None:
    _add_user(engine, "busy@iitk.ac.in")
    for _ in range(4):
        assert _login(db_client, "busy@iitk.ac.in", "typo").status_code == 401
    for _ in range(10):
        assert _login(db_client, "busy@iitk.ac.in", PASSWORD).status_code == 200

    # The four failures still count: one more is allowed, then the limit applies.
    assert _login(db_client, "busy@iitk.ac.in", "typo").status_code == 401
    assert _login(db_client, "busy@iitk.ac.in", "typo").status_code == 429


def test_nfr21_limit_resets_in_the_next_minute(
    db_client: TestClient, engine: Engine, now: Clock
) -> None:
    _add_user(engine, "victim@iitk.ac.in")
    for _ in range(5):
        _login(db_client, "victim@iitk.ac.in", "guess")
    assert _login(db_client, "victim@iitk.ac.in", PASSWORD).status_code == 429

    now.at += timedelta(seconds=50)

    assert _login(db_client, "victim@iitk.ac.in", PASSWORD).status_code == 200


def _student_headers(engine: Engine) -> dict[str, str]:
    student = _add_user(engine, f"s-{uuid.uuid4().hex[:8]}@iitk.ac.in")
    token = create_access_token(student.id, student.role)
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())}


def test_nfr21_eleventh_order_request_in_a_minute_gets_429(
    db_client: TestClient, engine: Engine, now: Clock
) -> None:
    student = _student_headers(engine)
    other = _student_headers(engine)
    missing = uuid.uuid4()

    # Create, modify and cancel share one counter. These fail after the limit check
    # (no such order, or an empty body), which still counts as a request.
    statuses = [
        db_client.post(f"/api/v1/orders/{missing}/cancel", json={}, headers=student).status_code
        for _ in range(5)
    ]
    statuses += [
        db_client.patch(f"/api/v1/orders/{missing}", json={}, headers=student).status_code
        for _ in range(3)
    ]
    statuses += [
        db_client.post("/api/v1/orders", json={}, headers=student).status_code for _ in range(2)
    ]
    assert 429 not in statuses

    refused = db_client.post(f"/api/v1/orders/{missing}/cancel", json={}, headers=student)
    assert refused.status_code == 429
    assert refused.headers["Retry-After"] == "50"
    # The limit is per Student.
    other_status = db_client.post(f"/api/v1/orders/{missing}/cancel", json={}, headers=other)
    assert other_status.status_code != 429


def test_nfr21_failed_logins_are_limited_across_api_processes(
    live_stack: LiveStack, engine: Engine
) -> None:
    """Twenty parallel guesses spread over two caf-api processes: exactly five are checked."""
    email = f"target-{uuid.uuid4().hex[:8]}@iitk.ac.in"
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE rate_limits"))

    async def guess(client: httpx.AsyncClient, n: int) -> int:
        url = live_stack.api_urls[n % len(live_stack.api_urls)] + LOGIN
        response = await client.post(url, json={"email": email, "password": f"guess-{n}"})
        return response.status_code

    async def burst() -> list[int]:
        async with httpx.AsyncClient(timeout=60) as client:
            return await asyncio.gather(*(guess(client, n) for n in range(20)))

    try:
        statuses = asyncio.run(burst())
    finally:
        with engine.begin() as connection:
            connection.execute(text("TRUNCATE rate_limits"))

    assert sorted(statuses) == [401] * 5 + [429] * 15


def test_nfr20_rejected_password_is_not_echoed_in_the_422(db_client: TestClient) -> None:
    response = db_client.post(
        "/api/v1/auth/register",
        json={"name": "A", "email": "a@iitk.ac.in", "password": "short7!"},
    )

    assert response.status_code == 422
    assert "short7!" not in response.text
    # Still field-level (NFR-22).
    [error] = response.json()["detail"]
    assert error["loc"] == ["body", "password"]
    assert error["type"] == "string_too_short"


def test_nfr20_password_is_never_logged_or_returned(
    db_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    password = "Distinctive-Pa55word"
    caplog.set_level(logging.DEBUG)

    registered = db_client.post(
        "/api/v1/auth/register",
        json={"name": "A", "email": "logs@iitk.ac.in", "password": password},
    )
    logged_in = _login(db_client, "logs@iitk.ac.in", password)
    failed = _login(db_client, "logs@iitk.ac.in", password + "x")

    assert (registered.status_code, logged_in.status_code, failed.status_code) == (201, 200, 401)
    for response in (registered, logged_in, failed):
        assert password not in response.text
        assert "password" not in response.json()
    assert password not in caplog.text


def test_nfr20_stored_password_is_an_argon2id_hash(db_client: TestClient, engine: Engine) -> None:
    db_client.post(
        "/api/v1/auth/register",
        json={"name": "A", "email": "hash@iitk.ac.in", "password": PASSWORD},
    )

    with Session(engine) as session:
        stored = session.scalars(
            select(User.password_hash).where(User.email == "hash@iitk.ac.in")
        ).one()
    assert stored.startswith("$argon2id$")
    assert PASSWORD not in stored


def test_old_windows_are_deleted_and_current_ones_kept(engine: Engine) -> None:
    now = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        session.execute(text("TRUNCATE rate_limits"))
        session.add_all(
            [
                RateLimit(subject="old", window_start=now - timedelta(days=3), count=5),
                RateLimit(subject="today", window_start=now, count=1),
            ]
        )

    with Session(engine) as session:
        deleted = RateLimiter(session, now=lambda: now).delete_old_windows()

    with Session(engine) as session:
        left: list[Any] = list(session.scalars(select(RateLimit.subject)))
        session.execute(text("TRUNCATE rate_limits"))
        session.commit()
    assert deleted == 1
    assert left == ["today"]
