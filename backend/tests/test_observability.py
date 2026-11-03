"""NFR-28 - NFR-30 tests TC-NFR28..30: JSON logs, the correlation ID and redaction."""

import io
import json
import logging
import re
import uuid
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session
from test_agent_run import Kitchen, kitchen  # noqa: F401  (kitchen is a fixture)

from app.core import context
from app.core.clock import IST
from app.core.logs import REDACTED, CafLogHandler, redact
from app.core.security import create_access_token
from app.models.enums import AgentRunStatus, AgentTrigger, Role
from app.models.identity import User
from app.models.platform import AuditLog
from app.modules.agent.orchestrator import PlanningOrchestrator
from app.modules.agent.service import AgentService
from app.modules.audit.service import write_audit
from app.modules.payments.mockpay_gateway import _forward_correlation_id
from app.worker.jobs import Job
from app.worker.main import _guarded

HEX_ID = re.compile(r"[0-9a-f]{32}")

Logs = Callable[[], list[dict[str, Any]]]


@pytest.fixture
def json_logs() -> Iterator[Logs]:
    """Every record logged during the test, as the JSON objects caf-api writes."""
    handler = CafLogHandler()
    stream = io.StringIO()
    handler.setStream(stream)
    root = logging.getLogger()
    root.addHandler(handler)
    level = root.level
    root.setLevel(logging.INFO)
    yield lambda: [json.loads(line) for line in stream.getvalue().splitlines()]
    root.removeHandler(handler)
    root.setLevel(level)


def _student(engine: Engine) -> User:
    user = User(
        id=uuid.uuid4(),
        name="Asha Verma",
        email=f"asha.{uuid.uuid4().hex[:8]}@iitk.ac.in",
        password_hash="unused",
        role=Role.STUDENT,
    )
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add(user)
    return user


def _bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


# --- NFR-29: the correlation ID -------------------------------------------------------


def test_tc_nfr29_the_clients_request_id_is_returned(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "client-req-42"})
    assert response.headers["X-Request-ID"] == "client-req-42"


@pytest.mark.parametrize("offered", [None, "", "has space", "x" * 129, "line\nbreak", "<script>"])
def test_tc_nfr29_the_server_assigns_an_id_when_none_or_an_unsafe_one_is_sent(
    client: TestClient, offered: str | None
) -> None:
    headers = {} if offered is None else {"X-Request-ID": offered}
    first = client.get("/health", headers=headers).headers["X-Request-ID"]
    second = client.get("/health", headers=headers).headers["X-Request-ID"]
    assert HEX_ID.fullmatch(first)
    assert first != second


def test_tc_nfr29_errors_carry_the_id_too(client: TestClient) -> None:
    response = client.get("/api/v1/orders", headers={"X-Request-ID": "req-401"})
    assert response.status_code == 401
    assert response.headers["X-Request-ID"] == "req-401"


def test_tc_nfr29_audit_rows_carry_the_requests_id(db_client: TestClient, engine: Engine) -> None:
    student = _student(engine)
    request_id = f"req-{uuid.uuid4().hex}"
    # A Student calling an Administrator endpoint is audited as a security event (FR-7).
    response = db_client.get(
        "/api/v1/admin/agent/runs", headers=_bearer(student) | {"X-Request-ID": request_id}
    )
    assert response.status_code == 403
    with Session(engine) as session:
        audited = session.scalars(
            select(AuditLog).where(AuditLog.correlation_id == request_id)
        ).all()
    assert [row.actor_id for row in audited] == [str(student.id)]


def test_tc_nfr29_an_explicit_audit_correlation_id_is_kept(engine: Engine) -> None:
    entity = uuid.uuid4().hex
    with context.correlation("req-outer"), Session(engine) as session, session.begin():
        write_audit(
            session, action="TEST", entity_type="test", entity_id=entity, correlation_id="p-1"
        )
        write_audit(session, action="TEST", entity_type="test", entity_id=entity)
    with Session(engine) as session:
        rows = session.scalars(
            select(AuditLog.correlation_id).where(AuditLog.entity_id == entity)
        ).all()
    assert sorted(str(row) for row in rows) == ["p-1", "req-outer"]


def test_tc_nfr29_mockpay_calls_carry_the_id() -> None:
    request = httpx.Request("POST", "http://mockpay/authorise")
    with context.correlation("req-pay"):
        _forward_correlation_id(request)
    assert request.headers["X-Request-ID"] == "req-pay"

    outside = httpx.Request("POST", "http://mockpay/authorise")
    _forward_correlation_id(outside)
    assert "X-Request-ID" not in outside.headers


def test_tc_nfr29_an_agent_run_records_the_id_of_the_request_that_queued_it(
    kitchen: Kitchen, db_client: TestClient, engine: Engine
) -> None:
    response = db_client.post(
        "/api/v1/admin/agent/runs",
        headers=kitchen.auth(kitchen.admin) | {"X-Request-ID": "req-agent"},
    )
    assert response.status_code == 202
    with engine.connect() as connection:
        stored = connection.scalar(
            text("SELECT correlation_id FROM agent_runs WHERE id = :id"),
            {"id": response.json()["id"]},
        )
    assert stored == "req-agent"


def test_tc_nfr29_the_worker_executes_an_agent_run_under_that_id(
    kitchen: Kitchen, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str | None] = []

    def execute(self: PlanningOrchestrator, *args: Any) -> AgentRunStatus:
        seen.append(context.correlation_id())
        return AgentRunStatus.SUCCEEDED

    monkeypatch.setattr(PlanningOrchestrator, "execute", execute)
    now = datetime(2026, 10, 6, 11, 30, tzinfo=IST)
    with Session(engine, expire_on_commit=False) as session:
        service = AgentService(session, lambda s: None)  # type: ignore[arg-type, return-value]
        with context.correlation("req-queued"):
            service.request_run(AgentTrigger.ON_DEMAND, kitchen.admin.id, now)
        # The worker runs it later, in a job with an ID of its own.
        with context.correlation("job-123"):
            assert service.run_next(now) is AgentRunStatus.SUCCEEDED
    assert seen == ["req-queued"]


def test_tc_nfr29_each_worker_job_run_has_its_own_id(json_logs: Logs) -> None:
    seen: list[str | None] = []

    def job() -> None:
        seen.append(context.correlation_id())
        raise RuntimeError("boom")

    run = _guarded(Job(name="probe", func=job, every_s=60))
    run()
    run()

    assert len(seen) == 2 and seen[0] != seen[1]
    assert all(cid and HEX_ID.fullmatch(cid) for cid in seen)
    # The failure is logged under the run's ID, after the job has returned.
    failures = [e for e in json_logs() if e["message"] == "job probe failed"]
    assert [e["correlation_id"] for e in failures] == seen
    assert context.correlation_id() is None


# --- NFR-28: structured JSON logs -------------------------------------------------------


def test_tc_nfr28_each_request_is_logged_as_json_with_the_required_fields(
    db_client: TestClient, engine: Engine, json_logs: Logs
) -> None:
    student = _student(engine)
    response = db_client.get(
        f"/api/v1/orders/{uuid.uuid4()}", headers=_bearer(student) | {"X-Request-ID": "req-28"}
    )
    assert response.status_code == 404

    access = [e for e in json_logs() if e["logger"] == "caf.access"]
    assert len(access) == 1
    entry = access[0]
    assert entry["level"] == "INFO"
    assert datetime.fromisoformat(entry["ts"]).tzinfo is not None
    assert entry["correlation_id"] == "req-28"
    assert entry["route"] == "/api/v1/orders/{order_id}"
    assert entry["method"] == "GET"
    assert entry["status"] == 404
    assert isinstance(entry["latency_ms"], float)
    assert entry["user_id"] == str(student.id)
    # The internal ID only, never the email or name.
    for line in json_logs():
        assert student.email not in json.dumps(line)
        assert student.name not in json.dumps(line)


def test_tc_nfr28_an_anonymous_request_has_no_user_id(client: TestClient, json_logs: Logs) -> None:
    client.get("/api/v1/orders")
    (entry,) = [e for e in json_logs() if e["logger"] == "caf.access"]
    assert entry["user_id"] is None
    assert entry["status"] == 401


def test_tc_nfr28_probes_are_not_logged_at_info(client: TestClient, json_logs: Logs) -> None:
    for path in ("/health", "/ready", "/metrics"):
        client.get(path)
    assert not [e for e in json_logs() if e["logger"] == "caf.access"]


# --- NFR-30: no secrets in logs ---------------------------------------------------------

JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
)


@pytest.mark.parametrize(
    ("logged", "secret"),
    [
        ("login failed: password=hunter2", "hunter2"),
        ('body {"email": "a@iitk.ac.in", "password": "hunter2"}', "hunter2"),
        ("{'new_password': 'hunter2'}", "hunter2"),
        (f"Authorization: Bearer {JWT}", JWT),
        (f"token {JWT} rejected", JWT),
        ('{"refresh_token": "r3fr3sh-t0k3n"}', "r3fr3sh-t0k3n"),
        ("CAF_LLM_API_KEY=sk-proj-abcdef0123456789", "sk-proj-abcdef0123456789"),
        ("api_key: my-key-value", "my-key-value"),
        ("X-API-Key=topsecret", "topsecret"),
        ("CAF_JWT_SECRET=a-very-long-signing-key", "a-very-long-signing-key"),
        ("connect postgresql+psycopg://caf:s3cretpw@db:5432/caf failed", "s3cretpw"),
        ("cache redis://:s3cretpw@cache:6379/0", "s3cretpw"),
        ("card 4111 1111 1111 1111 declined", "4111 1111 1111 1111"),
        ("card_number=4111111111111111", "4111111111111111"),
    ],
)
def test_tc_nfr30_secrets_are_redacted(logged: str, secret: str) -> None:
    redacted = redact(logged)
    assert secret not in redacted
    assert REDACTED in redacted
    # A record can pass through more than one handler.
    assert redact(redacted) == redacted


@pytest.mark.parametrize(
    "logged",
    [
        "llm call prompt_tokens=812 completion_tokens=120 latency_ms=40",
        "order 6f1c2a9e-1b7d-4c55-9a43-2f0c8d1e7b6a amount_paise=11000",
        "agent run 1234567890123456 queued",  # 16 digits, but not a card number (Luhn)
        "GET /api/v1/orders/{order_id} 404",
        # A port is not a password, even with an @ later in the URL.
        "GET http://localhost:8000/api/v1/users/asha@iitk.ac.in",
    ],
)
def test_tc_nfr30_ordinary_values_are_kept(logged: str) -> None:
    assert redact(logged) == logged


def test_tc_nfr30_the_filter_covers_args_extras_and_tracebacks(json_logs: Logs) -> None:
    log = logging.getLogger("caf.test")
    log.warning("login body %s", {"email": "a@iitk.ac.in", "password": "hunter2"})
    log.warning("refresh", extra={"refresh_token": "r3fr3sh", "detail": {"api_key": "k3y"}})
    try:
        raise ValueError(f"bad header Bearer {JWT}")
    except ValueError:
        log.exception("failed")

    written = json.dumps(json_logs())
    for secret in ("hunter2", "r3fr3sh", "k3y", JWT):
        assert secret not in written
    assert "a@iitk.ac.in" in written  # only secrets are removed


def test_tc_nfr30_a_mistyped_log_call_is_still_logged_and_never_raises(
    json_logs: Logs,
) -> None:
    log = logging.getLogger("caf.test")
    log.warning("%d portions left for password=%s", "many", "hunter2")

    (entry,) = [e for e in json_logs() if e["logger"] == "caf.test"]
    assert entry["message"] == (
        "%d portions left for password=[REDACTED] "
        "(arguments dropped: they did not fit the template)"
    )
    assert "hunter2" not in json.dumps(entry)


def test_tc_nfr30_a_failed_login_logs_no_password(db_client: TestClient, json_logs: Logs) -> None:
    password = "Corr3ct-Horse-Battery"
    response = db_client.post(
        "/api/v1/auth/login", json={"email": "nobody@iitk.ac.in", "password": password}
    )
    assert response.status_code == 401
    assert json_logs()  # the request was logged
    assert password not in json.dumps(json_logs())
