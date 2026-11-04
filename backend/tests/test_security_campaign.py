"""CAFIITK-185: adversarial and security test campaign against the real API.

Each test is an attack on the running application (in-process, real PostgreSQL)
and asserts the secure outcome:

- authorisation abuse: every real route against every role (FR-6, Table 4.1-A),
  and one Student acting on another Student's order;
- token misuse: forged, unsigned, expired, wrong-type and tampered tokens (NFR-19);
- mass assignment and malformed input (NFR-22);
- price and quantity tampering at checkout (FR-27, P-MAX_QTY);
- idempotency keys across Students (NFR-18).

Prompt injection and malformed agent output are covered by US-41 and US-42 in
test_agent_authority.py and test_agent_run.py.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any, cast
from zoneinfo import ZoneInfo

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.session import get_session
from app.main import create_app
from app.models.capacity import DailyInventory, ServiceDay, Slot
from app.models.catalogue import MenuItem
from app.models.enums import ItemCategory, Role
from app.models.identity import User
from app.models.ordering import Order
from app.models.platform import Setting
from app.modules.identity.permissions import ROLE_PERMISSIONS, Permission
from app.modules.payments.fake import FakePaymentGateway
from app.modules.payments.gateway import PaymentGateway, TransactionGuardedGateway
from app.modules.payments.mockpay_gateway import get_payment_gateway

IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 10, 6)
PLACED_AT = datetime(2026, 10, 6, 9, 0, tzinfo=IST)
THALI_PAISE = 8000

# Every route and the permission it needs; None means any authenticated user, and
# routes absent from the table are public. test_every_route_is_in_the_matrix fails
# when a route is added without being listed here.
ANY_USER = "any authenticated user"
PUBLIC = "public"
MATRIX: dict[tuple[str, str], Permission | str] = {
    ("GET", "/health"): PUBLIC,
    ("POST", "/api/v1/auth/register"): PUBLIC,
    ("POST", "/api/v1/auth/login"): PUBLIC,
    ("POST", "/api/v1/auth/refresh"): PUBLIC,
    ("POST", "/api/v1/auth/logout"): ANY_USER,
    ("GET", "/api/v1/auth/me"): ANY_USER,
    ("GET", "/api/v1/menu"): Permission.BROWSE_MENU,
    ("GET", "/api/v1/slots"): Permission.BROWSE_MENU,
    ("POST", "/api/v1/quotes"): Permission.MANAGE_OWN_ORDERS,
    ("POST", "/api/v1/orders"): Permission.MANAGE_OWN_ORDERS,
    ("GET", "/api/v1/orders"): Permission.VIEW_OWN_ORDERS,
    ("GET", "/api/v1/orders/{order_id}"): Permission.VIEW_OWN_ORDERS,
    ("PATCH", "/api/v1/orders/{order_id}"): Permission.MANAGE_OWN_ORDERS,
    ("POST", "/api/v1/orders/{order_id}/cancel"): Permission.MANAGE_OWN_ORDERS,
    ("POST", "/api/v1/orders/{order_id}/quote"): Permission.MANAGE_OWN_ORDERS,
    ("GET", "/api/v1/kitchen/queue"): Permission.OPERATE_KITCHEN,
    ("POST", "/api/v1/kitchen/orders/{order_id}/transitions"): Permission.OPERATE_KITCHEN,
    ("POST", "/api/v1/items/{item_id}/flag"): Permission.FLAG_ITEM,
    ("DELETE", "/api/v1/items/{item_id}/flag"): Permission.FLAG_ITEM,
    ("POST", "/api/v1/admin/items"): Permission.MANAGE_MENU,
    ("PATCH", "/api/v1/admin/items/{item_id}"): Permission.MANAGE_MENU,
    ("DELETE", "/api/v1/admin/items/{item_id}"): Permission.MANAGE_MENU,
    ("PUT", "/api/v1/admin/inventory/{service_date}/{item_id}"): Permission.MANAGE_CAPACITY,
    ("PUT", "/api/v1/admin/service-days/{service_date}"): Permission.MANAGE_CAPACITY,
    ("PATCH", "/api/v1/admin/slots/{slot_id}"): Permission.MANAGE_CAPACITY,
    ("GET", "/api/v1/admin/discount-rules"): Permission.MANAGE_PRICING,
    ("POST", "/api/v1/admin/discount-rules"): Permission.MANAGE_PRICING,
    ("PATCH", "/api/v1/admin/discount-rules/{rule_id}"): Permission.MANAGE_PRICING,
    ("GET", "/api/v1/admin/subsidy"): Permission.MANAGE_PRICING,
    ("PUT", "/api/v1/admin/subsidy"): Permission.MANAGE_PRICING,
    ("GET", "/api/v1/admin/students"): Permission.MANAGE_PRICING,
    ("PUT", "/api/v1/admin/users/{user_id}/eligibility"): Permission.MANAGE_PRICING,
    ("POST", "/api/v1/admin/orders/{order_id}/cancel"): Permission.CANCEL_ANY_ORDER,
    ("GET", "/api/v1/admin/orders"): Permission.VIEW_ALL,
    ("GET", "/api/v1/admin/utilisation"): Permission.VIEW_ALL,
    ("GET", "/api/v1/admin/audit"): Permission.VIEW_ALL,
    ("GET", "/api/v1/admin/users"): Permission.MANAGE_STAFF,
    ("POST", "/api/v1/admin/users"): Permission.MANAGE_STAFF,
    ("POST", "/api/v1/admin/users/{user_id}/deactivate"): Permission.MANAGE_STAFF,
    ("POST", "/api/v1/admin/users/{user_id}/reactivate"): Permission.MANAGE_STAFF,
    ("GET", "/api/v1/admin/agent/runs"): Permission.MANAGE_AGENT,
    ("POST", "/api/v1/admin/agent/runs"): Permission.MANAGE_AGENT,
    ("GET", "/api/v1/admin/agent/runs/{run_id}"): Permission.MANAGE_AGENT,
    ("GET", "/api/v1/admin/proposals"): Permission.MANAGE_AGENT,
    ("POST", "/api/v1/admin/proposals/{proposal_id}/approve"): Permission.MANAGE_AGENT,
    ("POST", "/api/v1/admin/proposals/{proposal_id}/reject"): Permission.MANAGE_AGENT,
}


@pytest.fixture(autouse=True)
def _restore_settings(engine: Engine) -> Iterator[None]:
    """The probes may change settings through the API (the fuzz sends valid values too).

    db_client's teardown keeps the seeded settings, so put them back for later tests.
    """
    with Session(engine) as session:
        saved = {row.key: row.value for row in session.scalars(select(Setting))}
    yield
    with Session(engine) as session, session.begin():
        session.execute(delete(Setting))
        session.add_all(Setting(key=key, value=value) for key, value in saved.items())


def _routes() -> set[tuple[str, str]]:
    paths = create_app().openapi()["paths"]
    return {(method.upper(), path) for path, operations in paths.items() for method in operations}


def _concrete(path: str) -> str:
    return (
        path.replace("{service_date}", DAY.isoformat())
        .replace("{order_id}", str(uuid.uuid4()))
        .replace("{item_id}", str(uuid.uuid4()))
        .replace("{run_id}", str(uuid.uuid4()))
        .replace("{proposal_id}", str(uuid.uuid4()))
        .replace("{slot_id}", str(uuid.uuid4()))
        .replace("{rule_id}", str(uuid.uuid4()))
        .replace("{user_id}", str(uuid.uuid4()))
    )


def _user(engine: Engine, role: Role = Role.STUDENT, *, active: bool = True) -> User:
    user = User(
        id=uuid.uuid4(),
        name="Probe",
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


def _headers(user: User, key: str | None = None) -> dict[str, str]:
    return _bearer(create_access_token(user.id, user.role)) | {
        "Idempotency-Key": key or uuid.uuid4().hex
    }


# --- Authorisation abuse ----------------------------------------------------------


def test_every_route_is_in_the_matrix() -> None:
    assert _routes() == set(MATRIX)


@pytest.mark.parametrize(("method", "path"), sorted(MATRIX))
def test_anonymous_callers_reach_only_public_routes(
    db_client: TestClient, method: str, path: str
) -> None:
    response = db_client.request(method, _concrete(path), json={})

    if MATRIX[(method, path)] == PUBLIC:
        assert response.status_code != 401
    else:
        assert response.status_code == 401, response.text


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize(("method", "path"), sorted(MATRIX))
def test_each_role_reaches_exactly_its_permitted_routes(
    db_client: TestClient, engine: Engine, role: Role, method: str, path: str
) -> None:
    needed = MATRIX[(method, path)]
    if needed == PUBLIC:
        pytest.skip("public route")
    response = db_client.request(
        method, _concrete(path), json={}, headers=_headers(_user(engine, role))
    )

    allowed = needed == ANY_USER or needed in ROLE_PERMISSIONS[role]
    if allowed:
        assert response.status_code not in (401, 403), response.text
    else:
        assert response.status_code == 403, response.text


@pytest.fixture
def thali(engine: Engine) -> dict[str, Any]:
    item = MenuItem(
        id=uuid.uuid4(), name="Thali", category=ItemCategory.MEAL, price_paise=THALI_PAISE
    )
    day = ServiceDay(
        service_date=DAY,
        window_start=time(12, 0),
        window_end=time(14, 30),
        slot_len_min=15,
        default_capacity=30,
    )
    slot = Slot(
        id=uuid.uuid4(),
        service_date=DAY,
        starts_at=datetime(2026, 10, 6, 12, 15, tzinfo=IST),
        ends_at=datetime(2026, 10, 6, 12, 30, tzinfo=IST),
        capacity=30,
    )
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add_all([item, day])
        session.flush()
        session.add_all([slot, DailyInventory(item_id=item.id, service_date=DAY, total=50)])
    return {"item": item, "slot": slot}


@pytest.fixture
def api(db_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(clock, "now", lambda: PLACED_AT)
    fake = FakePaymentGateway()

    def guarded(session: Annotated[Session, Depends(get_session)]) -> PaymentGateway:
        return TransactionGuardedGateway(fake, session)

    cast(FastAPI, db_client.app).dependency_overrides[get_payment_gateway] = guarded
    return db_client


def _order_body(thali: dict[str, Any], qty: int = 2, **extra: Any) -> dict[str, Any]:
    return {
        "slot_id": str(thali["slot"].id),
        "lines": [{"item_id": str(thali["item"].id), "qty": qty}],
        "quoted_payable_paise": qty * THALI_PAISE,
    } | extra


def _place(api: TestClient, student: User, thali: dict[str, Any]) -> dict[str, Any]:
    response = api.post("/api/v1/orders", json=_order_body(thali), headers=_headers(student))
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def test_a_student_cannot_see_or_change_another_students_order(
    api: TestClient, engine: Engine, thali: dict[str, Any]
) -> None:
    owner, intruder = _user(engine), _user(engine)
    order = _place(api, owner, thali)
    path = f"/api/v1/orders/{order['id']}"
    cart = {
        "slot_id": str(thali["slot"].id),
        "lines": [{"item_id": str(thali["item"].id), "qty": 1}],
    }
    change = cart | {"version": order["version"], "quoted_payable_paise": THALI_PAISE}

    attempts = [
        api.get(path, headers=_headers(intruder)),
        api.post(f"{path}/quote", json=cart, headers=_headers(intruder)),
        api.patch(path, json=change, headers=_headers(intruder)),
        api.post(f"{path}/cancel", json={"version": order["version"]}, headers=_headers(intruder)),
    ]

    # 404, not 403: the response must not reveal that the order exists (SRS 4.0).
    assert [response.status_code for response in attempts] == [404] * 4
    assert api.get(path, headers=_headers(owner)).json()["status"] == "ACCEPTED"


def test_a_deactivated_account_is_refused_with_a_valid_token(
    db_client: TestClient, engine: Engine
) -> None:
    user = _user(engine, Role.ADMIN, active=False)

    response = db_client.get("/api/v1/auth/me", headers=_headers(user))

    assert response.status_code == 401


# --- Token misuse ----------------------------------------------------------------


def _claims(user: User, **overrides: Any) -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "sub": str(user.id),
        "role": user.role.value,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    } | overrides


def _sign(claims: dict[str, Any], key: str | None = None, algorithm: str = "HS256") -> str:
    return jwt.encode(claims, key or get_settings().jwt_secret, algorithm=algorithm)


@pytest.mark.parametrize(
    "forge",
    [
        pytest.param(lambda u: _sign(_claims(u), key="another-secret-" + "y" * 32), id="wrong-key"),
        pytest.param(lambda u: jwt.encode(_claims(u), None, algorithm="none"), id="alg-none"),
        pytest.param(lambda u: _sign(_claims(u), algorithm="HS512"), id="other-alg"),
        pytest.param(
            lambda u: _sign(_claims(u, exp=datetime.now(UTC) - timedelta(seconds=1))), id="expired"
        ),
        pytest.param(lambda u: _sign(_claims(u, type="refresh")), id="wrong-type"),
        pytest.param(lambda u: _sign(_claims(u, sub=str(uuid.uuid4()))), id="unknown-user"),
        pytest.param(lambda u: _sign(_claims(u, sub="not-a-uuid")), id="malformed-sub"),
        pytest.param(lambda u: _sign({"sub": str(u.id), "exp": 9999999999}), id="missing-claims"),
        pytest.param(lambda u: _sign(_claims(u, type=None)), id="null-type"),
        pytest.param(lambda u: _sign(_claims(u, sub=["a"])), id="list-sub"),
        pytest.param(lambda u: "not.a.jwt", id="garbage"),
        pytest.param(lambda u: "", id="empty"),
    ],
)
def test_forged_or_misused_tokens_get_401(
    db_client: TestClient, engine: Engine, forge: Any
) -> None:
    user = _user(engine, Role.ADMIN)

    response = db_client.get("/api/v1/admin/proposals", headers=_bearer(forge(user)))

    assert response.status_code == 401, response.text


def test_a_role_claim_cannot_raise_privileges(db_client: TestClient, engine: Engine) -> None:
    """The role comes from the database, never from the token (FR-6)."""
    student = _user(engine)

    token = _sign(_claims(student, role=Role.ADMIN.value))
    response = db_client.get("/api/v1/admin/proposals", headers=_bearer(token))

    assert response.status_code == 403


def test_a_refresh_token_is_not_accepted_as_an_access_token(
    db_client: TestClient, engine: Engine
) -> None:
    db_client.post(
        "/api/v1/auth/register",
        json={"name": "A", "email": "rt@iitk.ac.in", "password": "correct-horse"},
    )
    tokens = db_client.post(
        "/api/v1/auth/login", json={"email": "rt@iitk.ac.in", "password": "correct-horse"}
    ).json()

    response = db_client.get("/api/v1/auth/me", headers=_bearer(tokens["refresh_token"]))

    assert response.status_code == 401


def test_a_logged_out_refresh_token_cannot_be_used(db_client: TestClient) -> None:
    db_client.post(
        "/api/v1/auth/register",
        json={"name": "A", "email": "out@iitk.ac.in", "password": "correct-horse"},
    )
    tokens = db_client.post(
        "/api/v1/auth/login", json={"email": "out@iitk.ac.in", "password": "correct-horse"}
    ).json()
    db_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers=_bearer(tokens["access_token"]),
    )

    response = db_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    assert response.status_code == 401


def test_logging_out_with_someone_elses_refresh_token_does_not_revoke_it(
    db_client: TestClient,
) -> None:
    pairs = []
    for email in ("victim@iitk.ac.in", "attacker@iitk.ac.in"):
        db_client.post(
            "/api/v1/auth/register",
            json={"name": "A", "email": email, "password": "correct-horse"},
        )
        pairs.append(
            db_client.post(
                "/api/v1/auth/login", json={"email": email, "password": "correct-horse"}
            ).json()
        )
    victim, attacker = pairs

    db_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": victim["refresh_token"]},
        headers=_bearer(attacker["access_token"]),
    )

    refreshed = db_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": victim["refresh_token"]}
    )
    assert refreshed.status_code == 200


# --- Mass assignment and malformed input -----------------------------------------


def test_registration_cannot_choose_a_role(db_client: TestClient) -> None:
    response = db_client.post(
        "/api/v1/auth/register",
        json={
            "name": "A",
            "email": "role@iitk.ac.in",
            "password": "correct-horse",
            "role": "ADMIN",
        },
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "extra",
    [
        {"status": "READY"},
        {"total_paise": 1},
        {"student_id": str(uuid.uuid4())},
    ],
)
def test_an_order_cannot_set_server_owned_fields(
    api: TestClient, engine: Engine, thali: dict[str, Any], extra: dict[str, Any]
) -> None:
    response = api.post(
        "/api/v1/orders", json=_order_body(thali, **extra), headers=_headers(_user(engine))
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "qty",
    [0, -1, 2**31, 2**63, 1.5, None],
)
def test_nonsense_quantities_are_422(
    api: TestClient, engine: Engine, thali: dict[str, Any], qty: Any
) -> None:
    body = _order_body(thali) | {"lines": [{"item_id": str(thali["item"].id), "qty": qty}]}

    response = api.post("/api/v1/orders", json=body, headers=_headers(_user(engine)))

    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/orders/not-a-uuid",
        "/api/v1/orders/' OR 1=1 --",
        "/api/v1/orders/..%2F..%2Fadmin",
    ],
)
def test_malformed_ids_are_422_or_404(db_client: TestClient, engine: Engine, path: str) -> None:
    response = db_client.get(path, headers=_headers(_user(engine)))

    assert response.status_code in (404, 422)


def test_sql_in_a_login_email_is_just_a_failed_login(db_client: TestClient) -> None:
    response = db_client.post(
        "/api/v1/auth/login",
        json={"email": "' OR '1'='1' --@iitk.ac.in", "password": "x' OR '1'='1"},
    )

    assert response.status_code == 401


def test_an_oversized_body_is_rejected_without_a_server_error(
    db_client: TestClient, engine: Engine
) -> None:
    admin = _user(engine, Role.ADMIN)
    body = {"name": "x" * 1_000_000, "category": "MEAL", "price_paise": 100}

    response = db_client.post("/api/v1/admin/items", json=body, headers=_headers(admin))

    assert response.status_code == 422


def test_a_body_that_is_not_json_is_refused_without_a_server_error(
    db_client: TestClient, engine: Engine
) -> None:
    response = db_client.post(
        "/api/v1/orders",
        content=b"\x00\xff not json",
        headers=_headers(_user(engine)) | {"Content-Type": "application/json"},
    )

    assert response.status_code in (400, 422)


# --- Price and quantity tampering ------------------------------------------------


def test_paying_less_than_the_price_is_refused(
    api: TestClient, engine: Engine, thali: dict[str, Any]
) -> None:
    body = _order_body(thali) | {"quoted_payable_paise": 1}

    response = api.post("/api/v1/orders", json=body, headers=_headers(_user(engine)))

    assert response.status_code == 409
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Order)) == 0


def test_splitting_an_item_over_lines_does_not_bypass_the_quantity_limit(
    api: TestClient, engine: Engine, thali: dict[str, Any]
) -> None:
    """P-MAX_QTY (3) is per item: two lines of the same item must not add up past it."""
    line = {"item_id": str(thali["item"].id), "qty": 2}
    body = _order_body(thali) | {"lines": [line, line], "quoted_payable_paise": 4 * THALI_PAISE}

    response = api.post("/api/v1/orders", json=body, headers=_headers(_user(engine)))

    assert response.status_code == 422, response.text


def test_a_quantity_above_p_max_qty_is_refused(
    api: TestClient, engine: Engine, thali: dict[str, Any]
) -> None:
    response = api.post(
        "/api/v1/orders", json=_order_body(thali, qty=4), headers=_headers(_user(engine))
    )

    assert response.status_code == 422, response.text


# --- Idempotency keys across Students --------------------------------------------


def test_another_students_idempotency_key_does_not_return_their_order(
    api: TestClient, engine: Engine, thali: dict[str, Any]
) -> None:
    owner, other = _user(engine), _user(engine)
    key = uuid.uuid4().hex
    first = api.post("/api/v1/orders", json=_order_body(thali), headers=_headers(owner, key))

    second = api.post("/api/v1/orders", json=_order_body(thali), headers=_headers(other, key))

    assert first.status_code == second.status_code == 201
    assert second.json()["id"] != first.json()["id"]


# --- NUL characters --------------------------------------------------------------
# PostgreSQL cannot store U+0000 in text, so a NUL that reaches a query fails there.


def test_a_nul_in_login_is_just_a_failed_login(db_client: TestClient) -> None:
    client = TestClient(db_client.app, raise_server_exceptions=False)
    for body in (
        {"email": "a\u0000@iitk.ac.in", "password": "correct-horse"},
        {"email": "a@iitk.ac.in", "password": "pass\u0000word"},
    ):
        assert client.post("/api/v1/auth/login", json=body).status_code in (401, 422), body


def test_a_nul_in_a_refresh_token_is_refused(db_client: TestClient) -> None:
    client = TestClient(db_client.app, raise_server_exceptions=False)

    response = client.post("/api/v1/auth/refresh", json={"refresh_token": "abc\u0000def"})

    assert response.status_code in (401, 422)


def test_a_nul_in_a_registration_is_422(db_client: TestClient) -> None:
    client = TestClient(db_client.app, raise_server_exceptions=False)
    for body in (
        {"name": "A\u0000B", "email": "nul@iitk.ac.in", "password": "correct-horse"},
        {"name": "A", "email": "nul@iitk.ac.in", "password": "correct\u0000horse"},
    ):
        assert client.post("/api/v1/auth/register", json=body).status_code in (201, 422), body


def test_a_nul_in_admin_and_kitchen_text_is_422(db_client: TestClient, engine: Engine) -> None:
    client = TestClient(db_client.app, raise_server_exceptions=False)
    admin = _headers(_user(engine, Role.ADMIN))
    item = client.post(
        "/api/v1/admin/items",
        json={"name": "Dosa", "category": "MEAL", "price_paise": 4000},
        headers=admin,
    ).json()

    responses = {
        "item name": client.post(
            "/api/v1/admin/items",
            json={"name": "Do\u0000sa", "category": "MEAL", "price_paise": 4000},
            headers=admin,
        ),
        "item description": client.post(
            "/api/v1/admin/items",
            json={"name": "Idli", "description": "\u0000", "category": "MEAL", "price_paise": 4000},
            headers=admin,
        ),
        "flag reason": client.post(
            f"/api/v1/items/{item['id']}/flag", json={"reason": "gas\u0000"}, headers=admin
        ),
        "reject reason": client.post(
            f"/api/v1/admin/proposals/{uuid.uuid4()}/reject",
            json={"reason": "no\u0000"},
            headers=admin,
        ),
    }

    assert {name: r.status_code for name, r in responses.items() if r.status_code >= 500} == {}


# --- Fuzzing every route ---------------------------------------------------------
# Hostile bodies, query parameters, path parameters and headers, sent by a caller
# who is allowed to use the route. Whatever is sent, the answer is never a 5xx.

HOSTILE_VALUES: list[Any] = [
    None,
    True,
    0,
    -1,
    2**31,
    2**63,
    -(2**63),
    10**30,
    1e308,
    -0.5,
    "",
    " ",
    "x" * 100_000,
    "\u0000",
    "' OR 1=1 --",
    "2026-02-30",
    "9999-12-31",
    "0001-01-01",
    "25:61",
    "00000000-0000-0000-0000-000000000000",
    [],
    {},
    [None],
    {"$gt": ""},
]
HOSTILE_BODIES: list[Any] = [None, [], "x", 1, {}, {"a": [{"b": {"c": [1] * 1000}}]}]
HOSTILE_QUERY = [
    "",
    "-1",
    "0",
    "99999999999999999999",
    "1e308",
    "' OR 1=1 --",
    "\u0000",
    "2026-02-30",
    "9999-12-31T23:59:59+14:00",
    "0001-01-01T00:00:00",
    "x" * 5000,
    "true",
]
HOSTILE_PATH = {
    "{service_date}": ["0001-01-01", "9999-12-31", "2026-02-30", "x"],
    "uuid": ["00000000-0000-0000-0000-000000000000", "not-a-uuid", "1" * 500],
}


def _caller(engine: Engine, method: str, path: str) -> dict[str, str]:
    needed = MATRIX[(method, path)]
    if needed in (PUBLIC, ANY_USER) or needed in ROLE_PERMISSIONS[Role.STUDENT]:
        return _headers(_user(engine))
    return _headers(_user(engine, Role.ADMIN))


def _schema_fields(path: str, method: str) -> list[str]:
    spec = create_app().openapi()
    operation = spec["paths"][path][method.lower()]
    ref = (
        operation.get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
        .get("$ref")
    )
    if not ref:
        return []
    schema = spec["components"]["schemas"][ref.rsplit("/", 1)[-1]]
    return list(schema.get("properties", {}))


def _query_params(path: str, method: str) -> list[str]:
    operation = create_app().openapi()["paths"][path][method.lower()]
    return [p["name"] for p in operation.get("parameters", []) if p["in"] == "query"]


def _server_errors(responses: list[tuple[str, Any]]) -> list[str]:
    return [f"{label} -> {r.status_code}" for label, r in responses if r.status_code >= 500]


@pytest.mark.parametrize(("method", "path"), sorted(MATRIX))
def test_hostile_bodies_never_cause_a_server_error(
    api: TestClient, engine: Engine, method: str, path: str
) -> None:
    client = TestClient(api.app, raise_server_exceptions=False)
    fields = _schema_fields(path, method)
    sent: list[tuple[str, Any]] = []
    for body in HOSTILE_BODIES:
        sent.append(
            (
                f"body {body!r:.40}",
                client.request(
                    method, _concrete(path), json=body, headers=_caller(engine, method, path)
                ),
            )
        )
    for value in HOSTILE_VALUES:
        for field in fields:
            sent.append(
                (
                    f"{field}={value!r:.40}",
                    client.request(
                        method,
                        _concrete(path),
                        json={field: value},
                        headers=_caller(engine, method, path),
                    ),
                )
            )
        if fields:
            sent.append(
                (
                    f"all fields={value!r:.40}",
                    client.request(
                        method,
                        _concrete(path),
                        json=dict.fromkeys(fields, value),
                        headers=_caller(engine, method, path),
                    ),
                )
            )

    assert _server_errors(sent) == []


@pytest.mark.parametrize(
    ("method", "path"), sorted(key for key in MATRIX if _query_params(key[1], key[0]))
)
def test_hostile_query_parameters_never_cause_a_server_error(
    api: TestClient, engine: Engine, method: str, path: str
) -> None:
    client = TestClient(api.app, raise_server_exceptions=False)
    headers = _caller(engine, method, path)
    sent = [
        (
            f"{name}={value!r:.40}",
            client.request(method, _concrete(path), params={name: value}, headers=headers),
        )
        for name in _query_params(path, method)
        for value in HOSTILE_QUERY
    ]

    assert _server_errors(sent) == []


@pytest.mark.parametrize(("method", "path"), sorted(key for key in MATRIX if "{" in key[1]))
def test_hostile_path_parameters_never_cause_a_server_error(
    api: TestClient, engine: Engine, method: str, path: str
) -> None:
    client = TestClient(api.app, raise_server_exceptions=False)
    headers = _caller(engine, method, path)
    sent = []
    for value in HOSTILE_PATH["{service_date}"]:
        url = _concrete(path.replace("{service_date}", value))
        sent.append((url, client.request(method, url, json={}, headers=headers)))
    for value in HOSTILE_PATH["uuid"]:
        url = path.replace("{service_date}", DAY.isoformat())
        for name in ("{order_id}", "{item_id}", "{run_id}", "{proposal_id}", "{slot_id}"):
            url = url.replace(name, value)
        for name in ("{rule_id}", "{user_id}"):
            url = url.replace(name, value)
        sent.append((url, client.request(method, url, json={}, headers=headers)))

    assert _server_errors(sent) == []


@pytest.mark.parametrize("key", ["", " ", "x" * 10_000, "' OR 1=1 --", "é", "a\tb"], ids=repr)
def test_hostile_idempotency_keys_never_cause_a_server_error(
    api: TestClient, engine: Engine, thali: dict[str, Any], key: str
) -> None:
    client = TestClient(api.app, raise_server_exceptions=False)
    headers = _headers(_user(engine))
    try:
        headers["Idempotency-Key"] = key
        response = client.post("/api/v1/orders", json=_order_body(thali), headers=headers)
    except UnicodeEncodeError:
        pytest.skip("not sendable as an HTTP header")

    assert response.status_code < 500, response.text
