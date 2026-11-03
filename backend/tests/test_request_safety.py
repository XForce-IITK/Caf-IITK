"""CAFIITK-183: strict request validation (NFR-22) and safe error responses (NFR-23).

NFR-22: every request body rejects unknown fields, and so does every query
string, with a field-level 422.
NFR-23: an error response never shows a traceback, SQL, a file path or an
internal ID; a 5xx body is a generic message and the correlation ID only.
"""

import typing
import uuid
from collections.abc import Iterator
from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.context import HEADER, SERVER_ERROR_MESSAGE
from app.core.security import create_access_token
from app.db.session import get_session
from app.main import app as caf_app
from app.main import create_app
from app.mockpay.main import app as mockpay_app
from app.mockpay.main import create_app as create_mockpay
from app.models.enums import Role
from app.models.identity import User


def _user(engine: Engine, role: Role) -> dict[str, str]:
    user = User(
        id=uuid.uuid4(),
        name="Safety",
        email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
        password_hash="unused",
        role=role,
    )
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add(user)
    return {
        "Authorization": f"Bearer {create_access_token(user.id, user.role)}",
        "Idempotency-Key": uuid.uuid4().hex,
    }


def _extra_forbidden(response: Any, loc: list[str]) -> None:
    assert response.status_code == 422, response.text
    [error] = response.json()["detail"]
    assert error["loc"] == loc
    assert error["type"] == "extra_forbidden"
    assert "input" not in error


# --- NFR-22: unknown body fields ------------------------------------------------------


def _models(annotation: Any, found: set[type[BaseModel]]) -> None:
    for arg in typing.get_args(annotation):
        _models(arg, found)
    is_model = isinstance(annotation, type) and issubclass(annotation, BaseModel)
    if is_model and annotation not in found:
        found.add(annotation)
        for field in annotation.model_fields.values():
            _models(field.annotation, found)


@pytest.mark.parametrize("application", [caf_app, mockpay_app], ids=["caf-api", "mockpay"])
def test_tc_nfr22_every_request_body_model_forbids_unknown_fields(application: FastAPI) -> None:
    """Structural: a new endpoint whose body model ignores extra fields fails here."""
    found: set[type[BaseModel]] = set()
    for route_context in iter_route_contexts(application.routes):
        route = route_context.original_route
        if isinstance(route, APIRoute):
            for param in route.dependant.body_params:
                _models(param.field_info.annotation, found)

    assert found, "no request bodies found"
    lax = sorted(m.__name__ for m in found if m.model_config.get("extra") != "forbid")
    assert lax == []


@pytest.mark.parametrize(
    ("role", "path", "body"),
    [
        (Role.STUDENT, "/api/v1/orders/{id}/cancel", {"version": 1, "refund_to": "elsewhere"}),
        (
            Role.ADMIN,
            "/api/v1/admin/orders/{id}/cancel",
            {"version": 1, "reason": "duplicate", "refund_to": "elsewhere"},
        ),
        (Role.ADMIN, "/api/v1/admin/proposals/{id}/reject", {"reason": "no", "refund_to": "x"}),
    ],
    ids=["cancel", "admin-cancel", "reject-proposal"],
)
def test_tc_nfr22_an_unknown_body_field_is_a_field_level_422(
    db_client: TestClient, engine: Engine, role: Role, path: str, body: dict[str, Any]
) -> None:
    response = db_client.post(path.format(id=uuid.uuid4()), json=body, headers=_user(engine, role))

    _extra_forbidden(response, ["body", "refund_to"])


# --- NFR-22: unknown query parameters -------------------------------------------------


def test_tc_nfr22_an_unknown_query_parameter_is_a_field_level_422(
    db_client: TestClient, engine: Engine
) -> None:
    # A typo of `limit` used to be ignored and the default limit applied.
    response = db_client.get(
        "/api/v1/orders", params={"limt": 5}, headers=_user(engine, Role.STUDENT)
    )

    _extra_forbidden(response, ["query", "limt"])


def test_tc_nfr22_declared_query_parameters_are_still_accepted(
    db_client: TestClient, engine: Engine
) -> None:
    response = db_client.get(
        "/api/v1/orders", params={"limit": 5}, headers=_user(engine, Role.STUDENT)
    )

    assert response.status_code == 200, response.text


def test_tc_nfr22_each_unknown_query_parameter_is_reported_once() -> None:
    app = create_app()

    @app.get("/probe")
    def probe(size: int = 10) -> int:
        return size

    response = TestClient(app).get("/probe?size=2&b=1&a=1&b=2")

    assert response.status_code == 422
    assert [e["loc"] for e in response.json()["detail"]] == [["query", "b"], ["query", "a"]]


def test_tc_nfr22_query_parameters_of_dependencies_count_as_declared() -> None:
    app = create_app()

    def page(offset: Annotated[int, Query()] = 0) -> int:
        return offset

    @app.get("/probe")
    def probe(
        offset: Annotated[int, Depends(page)], size: Annotated[int, Query(alias="n")] = 1
    ) -> list[int]:
        return [offset, size]

    client = TestClient(app)

    assert client.get("/probe?offset=3&n=4").json() == [3, 4]
    assert client.get("/probe?size=4").status_code == 422  # only the alias is the parameter


# --- NFR-23: unhandled exceptions -----------------------------------------------------

_LEAKY = (
    'psycopg.errors.UndefinedTable: relation "orders_secret" does not exist '
    "LINE 1: SELECT id FROM orders_secret WHERE student_id = "
    "'6f1c2d4e-0000-4000-8000-000000000001' "
    "(/Users/someone/caf/backend/app/modules/ordering/service.py, line 42)"
)


@pytest.fixture
def failing_app() -> FastAPI:
    app = create_app()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError(_LEAKY)

    return app


def _generic_500(response: Any) -> None:
    assert response.status_code == 500
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {
        "detail": SERVER_ERROR_MESSAGE,
        "correlation_id": response.headers[HEADER],
    }
    for leak in ("Traceback", "orders_secret", "SELECT", "6f1c2d4e", "/Users/", ".py"):
        assert leak not in response.text


def test_tc_nfr23_an_unhandled_error_is_a_generic_500_with_the_correlation_id(
    failing_app: FastAPI,
) -> None:
    # Not raised into the test: the middleware answers it.
    response = TestClient(failing_app).get("/boom", headers={HEADER: "support-ticket-1"})

    _generic_500(response)
    assert response.json()["correlation_id"] == "support-ticket-1"


def test_tc_nfr23_the_details_are_logged_under_the_same_correlation_id(
    failing_app: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    response = TestClient(failing_app).get("/boom")

    [record] = [r for r in caplog.records if r.getMessage() == "unhandled error"]
    assert record.exc_info is not None and _LEAKY in str(record.exc_info[1])
    assert record.correlation_id == response.json()["correlation_id"]  # type: ignore[attr-defined]


def test_tc_nfr23_a_database_error_never_reaches_the_client(engine: Engine) -> None:
    app = create_app()
    factory = sessionmaker(bind=engine)

    def session() -> Iterator[Session]:
        with factory() as s:
            yield s

    @app.get("/broken-query")
    def broken_query(s: Annotated[Session, Depends(get_session)]) -> None:
        s.execute(text("SELECT id FROM orders_secret WHERE student_id = :id"), {"id": "6f1c2d4e"})

    app.dependency_overrides[get_session] = session

    _generic_500(TestClient(app).get("/broken-query"))


def test_tc_nfr23_mockpay_errors_are_generic_too() -> None:
    app = create_mockpay()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError(_LEAKY)

    _generic_500(TestClient(app).get("/boom"))


def test_tc_nfr23_an_error_after_the_response_started_is_not_answered_twice() -> None:
    app = create_app()

    def chunks() -> Iterator[bytes]:
        yield b"partial"
        raise RuntimeError(_LEAKY)

    @app.get("/stream")
    def stream() -> StreamingResponse:
        return StreamingResponse(chunks())

    # The 200 is already on the wire; a second response would be a protocol error.
    with pytest.raises(RuntimeError):
        TestClient(app).get("/stream")


# --- NFR-23: deliberate errors --------------------------------------------------------


def test_tc_nfr23_a_deliberate_503_keeps_its_message_and_headers_and_adds_the_id() -> None:
    app = create_app()

    @app.get("/busy")
    def busy() -> None:
        raise HTTPException(503, "Busy, try again", headers={"Retry-After": "1"})

    response = TestClient(app).get("/busy")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    assert response.json() == {
        "detail": "Busy, try again",
        "correlation_id": response.headers[HEADER],
    }


def test_tc_nfr23_a_structured_5xx_detail_is_replaced_by_the_generic_message() -> None:
    app = create_app()

    @app.get("/gateway")
    def gateway() -> None:
        raise HTTPException(502, {"upstream": "http://mockpay:8001", "order_id": "6f1c2d4e"})

    response = TestClient(app).get("/gateway")

    assert response.status_code == 502
    assert response.json() == {
        "detail": SERVER_ERROR_MESSAGE,
        "correlation_id": response.headers[HEADER],
    }


def test_tc_nfr23_the_database_down_503_carries_the_correlation_id() -> None:
    app = create_app()

    @app.get("/down")
    def down() -> None:
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    response = TestClient(app).get("/down")

    assert response.status_code == 503
    body = response.json()
    assert body["correlation_id"] == response.headers[HEADER]
    assert set(body) == {"detail", "correlation_id"}
    assert "SELECT" not in response.text


def test_tc_nfr23_4xx_responses_are_unchanged() -> None:
    app = create_app()

    @app.get("/missing")
    def missing() -> None:
        raise HTTPException(404, "Order not found")

    client = TestClient(app)

    assert client.get("/missing").json() == {"detail": "Order not found"}
    assert client.get("/no-such-route").json() == {"detail": "Not Found"}
