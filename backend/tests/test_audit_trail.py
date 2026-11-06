"""US-38 (CAFIITK-163; FR-47 - FR-49, NFR-26) acceptance tests TC-US38-AC1..AC4 via
GET /api/v1/admin/audit and the caf_app database role.
"""

import json
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any, cast
from zoneinfo import ZoneInfo

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from psycopg.errors import InsufficientPrivilege
from sqlalchemy import Engine, delete, text, update
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from app.core import clock
from app.core.security import create_access_token
from app.db.session import get_session, run_as_app_role
from app.main import create_app
from app.models.capacity import DailyInventory, ServiceDay, Slot
from app.models.catalogue import MenuItem
from app.models.enums import ItemCategory, Role
from app.models.identity import User
from app.models.platform import AuditLog
from app.modules.payments.fake import FakePaymentGateway
from app.modules.payments.gateway import PaymentGateway, TransactionGuardedGateway
from app.modules.payments.mockpay_gateway import get_payment_gateway

URL = "/api/v1/admin/audit"
IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 10, 6)
NOW = datetime(2026, 10, 6, 9, 0, tzinfo=IST)


def _add(engine: Engine, *rows: Any) -> None:
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add_all(rows)


def _user(engine: Engine, role: Role) -> User:
    user = User(
        id=uuid.uuid4(),
        name=f"{role.value} user",
        email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
        password_hash="unused",
        role=role,
    )
    _add(engine, user)
    return user


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


@pytest.fixture
def admin(engine: Engine) -> dict[str, str]:
    return _auth(_user(engine, Role.ADMIN))


@pytest.fixture
def thali(engine: Engine) -> MenuItem:
    item = MenuItem(id=uuid.uuid4(), name="Thali", category=ItemCategory.MEAL, price_paise=8000)
    _add(engine, item)
    return item


@pytest.fixture
def slot(
    db_client: TestClient, engine: Engine, thali: MenuItem, monkeypatch: pytest.MonkeyPatch
) -> Slot:
    slot = Slot(
        id=uuid.uuid4(),
        service_date=DAY,
        starts_at=datetime(2026, 10, 6, 12, 15, tzinfo=IST),
        ends_at=datetime(2026, 10, 6, 12, 30, tzinfo=IST),
        capacity=30,
    )
    _add(
        engine,
        ServiceDay(
            service_date=DAY,
            window_start=time(12, 0),
            window_end=time(14, 30),
            slot_len_min=15,
            default_capacity=30,
        ),
    )
    _add(engine, slot, DailyInventory(item_id=thali.id, service_date=DAY, total=10))
    monkeypatch.setattr(clock, "now", lambda: NOW)
    gateway = FakePaymentGateway()

    def guarded(session: Annotated[Session, Depends(get_session)]) -> PaymentGateway:
        return TransactionGuardedGateway(gateway, session)

    cast(FastAPI, db_client.app).dependency_overrides[get_payment_gateway] = guarded
    return slot


def _search(client: TestClient, headers: dict[str, str], **params: Any) -> dict[str, Any]:
    response = client.get(URL, params=params, headers=headers)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_tc_us38_ac1_order_placed_and_cancelled_shows_both_transitions_in_full(
    db_client: TestClient,
    engine: Engine,
    admin: dict[str, str],
    thali: MenuItem,
    slot: Slot,
) -> None:
    student = _user(engine, Role.STUDENT)
    placed = db_client.post(
        "/api/v1/orders",
        json={
            "slot_id": str(slot.id),
            "lines": [{"item_id": str(thali.id), "qty": 2}],
            "quoted_payable_paise": 16000,
        },
        headers=_auth(student) | {"Idempotency-Key": uuid.uuid4().hex, "X-Request-ID": "place-1"},
    )
    assert placed.status_code == 201, placed.text
    order = placed.json()
    cancelled = db_client.post(
        f"/api/v1/orders/{order['id']}/cancel",
        json={"version": order["version"]},
        headers=_auth(student) | {"Idempotency-Key": uuid.uuid4().hex, "X-Request-ID": "cancel-1"},
    )
    assert cancelled.status_code == 200, cancelled.text

    entries = _search(db_client, admin, entity_id=order["id"])["entries"]

    # Newest first; read oldest first like a history.
    entries.reverse()
    transitions = [
        (e["before"]["status"], e["after"]["status"], e["actor_role"], e["correlation_id"])
        for e in entries
        if e["action"] == "ORDER_TRANSITION"
    ]
    # The payment result, not the Student, moves the order to ACCEPTED.
    assert transitions == [
        (None, "PENDING_PAYMENT", "STUDENT", "place-1"),
        ("PENDING_PAYMENT", "ACCEPTED", "SYSTEM", "place-1"),
        ("ACCEPTED", "CANCELLED", "STUDENT", "cancel-1"),
    ]
    counts = [
        (e["action"], e["before"], e["after"], e["correlation_id"])
        for e in entries
        if e["action"] != "ORDER_TRANSITION"
    ]
    assert counts == [
        (
            "PORTIONS_ALLOCATED",
            {"allocated": 0},
            {"allocated": 2, "order_id": order["id"]},
            "place-1",
        ),
        ("SEAT_ALLOCATED", {"booked": 0}, {"booked": 1, "order_id": order["id"]}, "place-1"),
        (
            "PORTIONS_RELEASED",
            {"allocated": 2},
            {"allocated": 0, "order_id": order["id"]},
            "cancel-1",
        ),
        ("SEAT_RELEASED", {"booked": 1}, {"booked": 0, "order_id": order["id"]}, "cancel-1"),
        (
            "REFUND_RECORDED",
            None,
            {"cause": "CANCEL", "order_id": order["id"], "amount_paise": 16000},
            "cancel-1",
        ),
    ]
    for entry in entries:
        expected = (
            (None, "SYSTEM") if entry["actor_role"] == "SYSTEM" else (str(student.id), "STUDENT")
        )
        assert (entry["actor_id"], entry["actor_role"]) == expected
        assert datetime.fromisoformat(entry["at"]) > datetime.now(UTC) - timedelta(minutes=5)


def test_tc_us38_ac2_price_change_appears_with_before_and_after_price(
    db_client: TestClient, admin: dict[str, str], thali: MenuItem
) -> None:
    changed = db_client.patch(
        f"/api/v1/admin/items/{thali.id}",
        json={"price_paise": 9000},
        headers=admin | {"X-Request-ID": "price-1"},
    )
    assert changed.status_code == 200, changed.text

    [entry] = _search(db_client, admin, entity_type="menu_item", entity_id=str(thali.id))["entries"]

    assert (entry["action"], entry["actor_role"], entry["correlation_id"]) == (
        "ITEM_UPDATED",
        "ADMIN",
        "price-1",
    )
    assert (entry["before"], entry["after"]) == ({"price_paise": 8000}, {"price_paise": 9000})


def _as_app_role(engine: Engine, statement: Any) -> None:
    with Session(engine) as session, session.begin():
        session.execute(text("SET LOCAL ROLE caf_app"))
        session.execute(statement)


@pytest.mark.parametrize(
    "statement",
    [
        update(AuditLog).values(action="TAMPERED"),
        delete(AuditLog),
        text("TRUNCATE audit_log"),
    ],
    ids=["update", "delete", "truncate"],
)
def test_tc_us38_ac3_the_application_role_cannot_change_an_audit_entry(
    db_client: TestClient, engine: Engine, admin: dict[str, str], thali: MenuItem, statement: Any
) -> None:
    db_client.patch(f"/api/v1/admin/items/{thali.id}", json={"price_paise": 9000}, headers=admin)

    with pytest.raises(ProgrammingError) as refused:
        _as_app_role(engine, statement)

    assert isinstance(refused.value.orig, InsufficientPrivilege)
    [entry] = _search(db_client, admin, entity_id=str(thali.id))["entries"]
    assert entry["action"] == "ITEM_UPDATED"


def test_the_applications_sessions_run_as_caf_app(engine: Engine) -> None:
    factory = run_as_app_role(sessionmaker(bind=engine))

    with factory() as session, session.begin():
        assert session.scalar(text("SELECT current_user")) == "caf_app"
        with pytest.raises(ProgrammingError):
            session.execute(update(AuditLog).values(action="TAMPERED"))


def test_the_application_role_may_still_add_and_read_entries(engine: Engine) -> None:
    with Session(engine) as session, session.begin():
        session.execute(text("SET LOCAL ROLE caf_app"))
        session.add(AuditLog(action="TEST", entity_type="test"))
        session.flush()
        assert session.scalar(text("SELECT count(*) FROM audit_log WHERE action = 'TEST'")) == 1
        session.rollback()


def test_no_api_route_changes_the_audit_log() -> None:
    paths = create_app().openapi()["paths"]

    audit = {path: set(methods) for path, methods in paths.items() if "audit" in path}
    assert audit == {"/api/v1/admin/audit": {"get"}}


def test_tc_us38_ac4_no_password_token_or_secret_appears_in_results(
    db_client: TestClient, engine: Engine, admin: dict[str, str]
) -> None:
    password = "correct-horse-battery"
    tag = uuid.uuid4().hex
    registered = db_client.post(
        "/api/v1/auth/register",
        json={"name": "Asha", "email": "asha.audit@iitk.ac.in", "password": password},
    )
    assert registered.status_code == 201, registered.text
    db_client.post(
        "/api/v1/auth/login", json={"email": "asha.audit@iitk.ac.in", "password": "wrong-guess-1"}
    )
    tokens = db_client.post(
        "/api/v1/auth/login", json={"email": "asha.audit@iitk.ac.in", "password": password}
    ).json()
    db_client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    # A careless entry, written straight to the table: the search still hides it.
    _add(
        engine,
        AuditLog(
            action="CARELESS",
            entity_type="test",
            entity_id=tag,
            after={
                "password": password,
                "note": f"Authorization: Bearer {tokens['access_token']}",
                "refresh_token": tokens["refresh_token"],
            },
        ),
    )

    body = json.dumps(_search(db_client, admin, limit=200))

    for secret in (password, "wrong-guess-1", tokens["access_token"], tokens["refresh_token"]):
        assert secret not in body
    [careless] = _search(db_client, admin, action="CARELESS", entity_id=tag)["entries"]
    assert careless["after"]["password"] == "[REDACTED]"
    assert careless["after"]["refresh_token"] == "[REDACTED]"
    assert careless["after"]["note"].startswith("Authorization: [REDACTED]")


def _entries(engine: Engine, *rows: AuditLog) -> list[int]:
    _add(engine, *rows)
    return [row.id for row in rows]


def test_search_by_actor_action_type_and_time_range(
    db_client: TestClient, engine: Engine, admin: dict[str, str]
) -> None:
    # audit_log is never emptied between tests, so this test's values are its own.
    tag = uuid.uuid4().hex[:8]
    early = datetime(2026, 10, 6, 8, 0, tzinfo=UTC)
    late = datetime(2026, 10, 6, 10, 0, tzinfo=UTC)
    a, b, c = _entries(
        engine,
        AuditLog(at=early, actor_id=f"u1-{tag}", action=f"ONE_{tag}", entity_type=f"slot-{tag}"),
        AuditLog(at=late, actor_id=f"u1-{tag}", action=f"TWO_{tag}", entity_type=f"slot-{tag}"),
        AuditLog(at=late, actor_id=f"u2-{tag}", action=f"ONE_{tag}", entity_type=f"order-{tag}"),
    )

    def ids(**params: Any) -> list[int]:
        return [e["id"] for e in _search(db_client, admin, **params)["entries"]]

    assert ids(actor_id=f"u1-{tag}") == [b, a]
    assert ids(action=f"ONE_{tag}") == [c, a]
    assert ids(entity_type=f"slot-{tag}") == [b, a]
    window = {"from": "2026-10-06T09:00:00Z", "to": "2026-10-06T11:00:00Z"}
    assert ids(**window, actor_id=f"u1-{tag}") == [b]
    earlier = {"from": "2026-10-06T08:00:00Z", "to": "2026-10-06T10:00:00Z"}
    assert ids(**earlier, entity_type=f"slot-{tag}") == [a]


def test_results_come_a_page_at_a_time(
    db_client: TestClient, engine: Engine, admin: dict[str, str]
) -> None:
    action = f"PAGED_{uuid.uuid4().hex[:8]}"
    ids = _entries(engine, *[AuditLog(action=action, entity_type="test") for _ in range(5)])

    first = _search(db_client, admin, action=action, limit=2)
    second = _search(db_client, admin, action=action, limit=2, before_id=first["next_before_id"])
    last = _search(db_client, admin, action=action, limit=2, before_id=second["next_before_id"])

    pages = [[e["id"] for e in page["entries"]] for page in (first, second, last)]
    assert pages == [ids[4:2:-1], ids[2:0:-1], ids[:1]]
    assert last["next_before_id"] is None


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2026-10-06T10:00:00Z", "to": "2026-10-06T10:00:00Z"},
        {"limit": 0},
        {"limit": 201},
        {"before_id": 0},
        {"from": "yesterday"},
    ],
)
def test_invalid_search_is_422(
    db_client: TestClient, admin: dict[str, str], params: dict[str, Any]
) -> None:
    assert db_client.get(URL, params=params, headers=admin).status_code == 422


@pytest.mark.parametrize("role", [Role.KITCHEN, Role.STUDENT])
def test_only_the_administrator_searches_the_log(
    db_client: TestClient, engine: Engine, role: Role
) -> None:
    assert db_client.get(URL, headers=_auth(_user(engine, role))).status_code == 403


def test_searching_requires_a_token(db_client: TestClient) -> None:
    assert db_client.get(URL).status_code == 401
