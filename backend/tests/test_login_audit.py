"""CAFIITK-205 (FR-47): a failed login is written to the audit log as a security event."""

from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.security import hash_password
from app.models.enums import Role
from app.models.identity import User
from app.models.platform import AuditLog

PASSWORD = "correct-horse"
LOGIN = "/api/v1/auth/login"


@pytest.fixture(autouse=True)
def _fixed_minute(monkeypatch: pytest.MonkeyPatch) -> None:
    # Every attempt in a test falls in the same NFR-21 window.
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 5, 12, 0, 10, tzinfo=clock.IST))


def _add_user(engine: Engine, email: str) -> User:
    with Session(engine, expire_on_commit=False) as session, session.begin():
        user = User(name="U", email=email, password_hash=hash_password(PASSWORD), role=Role.STUDENT)
        session.add(user)
    return user


@pytest.fixture(autouse=True)
def _audit_baseline(engine: Engine) -> None:
    # audit_log is append-only and outlives each test, so count only this test's rows.
    global _BASELINE
    with Session(engine) as session:
        _BASELINE = session.scalar(select(func.coalesce(func.max(AuditLog.id), 0))) or 0


_BASELINE = 0


def _failed_logins(engine: Engine) -> list[AuditLog]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(AuditLog)
                .where(AuditLog.action == "LOGIN_FAILED", AuditLog.id > _BASELINE)
                .order_by(AuditLog.id)
            )
        )


def _login(client: TestClient, email: str, password: str) -> Any:
    return client.post(LOGIN, json={"email": email, "password": password})


def test_a_wrong_password_is_audited_against_the_account(
    db_client: TestClient, engine: Engine
) -> None:
    user = _add_user(engine, "victim@iitk.ac.in")

    response = _login(db_client, "victim@iitk.ac.in", "guess-1")

    assert response.status_code == 401
    [entry] = _failed_logins(engine)
    assert (entry.entity_type, entry.entity_id) == ("user", str(user.id))
    assert entry.actor_id is None
    assert entry.after is not None
    assert entry.after["account"] == "existing"
    assert entry.after["client_ip"] == "testclient"
    assert entry.correlation_id == response.headers["X-Request-ID"]
    assert "guess-1" not in str(entry.after)


def test_an_unknown_email_is_audited_by_its_hash_only(
    db_client: TestClient, engine: Engine
) -> None:
    _login(db_client, "nobody@iitk.ac.in", "guess")

    [entry] = _failed_logins(engine)
    assert (entry.entity_type, entry.entity_id) == ("security", None)
    assert entry.after is not None
    assert entry.after["account"] == "unknown"
    assert entry.after["account_subject"].startswith("login-account:")
    assert "nobody" not in str(entry.after)


def test_a_deactivated_account_failing_is_audited(db_client: TestClient, engine: Engine) -> None:
    user = _add_user(engine, "gone@iitk.ac.in")
    with Session(engine) as session, session.begin():
        session.get_one(User, user.id).is_active = False

    assert _login(db_client, "gone@iitk.ac.in", PASSWORD).status_code == 401

    [entry] = _failed_logins(engine)
    assert entry.entity_id == str(user.id)


def test_a_successful_login_is_not_audited(db_client: TestClient, engine: Engine) -> None:
    _add_user(engine, "ok@iitk.ac.in")

    assert _login(db_client, "ok@iitk.ac.in", PASSWORD).status_code == 200

    assert _failed_logins(engine) == []


def test_logins_refused_by_the_limit_add_no_rows(db_client: TestClient, engine: Engine) -> None:
    """The NFR-21 limit bounds the audit rows an attacker can cause."""
    _add_user(engine, "target@iitk.ac.in")

    statuses = [_login(db_client, "target@iitk.ac.in", f"guess-{n}").status_code for n in range(8)]

    assert statuses == [401] * 5 + [429] * 3
    assert len(_failed_logins(engine)) == 5


def test_failed_logins_are_found_by_audit_search(db_client: TestClient, engine: Engine) -> None:
    from app.core.security import create_access_token

    _add_user(engine, "victim@iitk.ac.in")
    _login(db_client, "victim@iitk.ac.in", "guess")
    with Session(engine, expire_on_commit=False) as session, session.begin():
        admin = User(name="A", email="a@iitk.ac.in", password_hash="x", role=Role.ADMIN)
        session.add(admin)
    headers = {"Authorization": f"Bearer {create_access_token(admin.id, admin.role)}"}

    found = db_client.get(
        "/api/v1/admin/audit", params={"action": "LOGIN_FAILED", "limit": 1}, headers=headers
    ).json()

    [latest] = found["entries"]
    assert latest["action"] == "LOGIN_FAILED"
    assert latest["id"] == _failed_logins(engine)[-1].id
