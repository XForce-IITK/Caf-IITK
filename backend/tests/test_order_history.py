"""US-21 (FR-27, FR-28) acceptance tests TC-US21-AC1..AC2, and GET /api/v1/orders.

The fixtures come from the modify tests: a Thali and a Tea in the 12:15 slot.
"""

import uuid
from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from test_order_modify import TEA, THALI, Clock, _cart, _headers, _modify, _place, _student
from test_order_modify import api as api  # noqa: F401 - fixtures, found by name
from test_order_modify import gateway as gateway  # noqa: F401
from test_order_modify import menu as menu  # noqa: F401
from test_order_modify import now as now  # noqa: F401

from app.models.enums import Role


def _detail(api: TestClient, student: Any, order_id: str) -> dict[str, Any]:
    response = api.get(f"/api/v1/orders/{order_id}", headers=_headers(student))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_tc_us21_ac1_a_modified_order_shows_v1_as_shown_originally_and_v2(
    api: TestClient, engine: Engine, menu: dict[str, Any], now: Clock
) -> None:
    student = _student(engine)
    quoted = api.post(
        "/api/v1/quotes", json=_cart(menu, thali=1, tea=1), headers=_headers(student)
    ).json()
    order = _place(api, student, menu, THALI + TEA)
    now.now += timedelta(minutes=5)
    modified = _modify(api, student, order, _cart(menu, thali=2), 2 * THALI)
    assert modified.status_code == 200, modified.text

    detail = _detail(api, student, order["id"])

    assert [snapshot["version"] for snapshot in detail["snapshots"]] == [1, 2]
    v1, v2 = detail["snapshots"]
    # What the Student was shown before confirming, unchanged by the modification.
    assert v1["price"] == quoted
    assert v1["price"]["payable_paise"] == THALI + TEA
    assert v2["price"]["payable_paise"] == 2 * THALI
    assert v1["priced_at"] < v2["priced_at"]
    # The order itself shows the latest snapshot.
    assert detail["price"] == v2["price"]
    assert detail["refunds"] == []


def test_tc_us21_ac2_a_cancelled_order_shows_its_refund_amount_and_time(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    student = _student(engine)
    order = _place(api, student, menu, THALI + TEA)
    cancelled = api.post(
        f"/api/v1/orders/{order['id']}/cancel",
        json={"version": order["version"]},
        headers=_headers(student),
    )
    assert cancelled.status_code == 200, cancelled.text

    detail = _detail(api, student, order["id"])

    [refund] = detail["refunds"]
    assert refund["amount_paise"] == THALI + TEA
    assert refund["cause"] == "CANCEL"
    assert refund["status"] == "SUCCEEDED"
    assert refund["at"]
    assert detail["status"] == "CANCELLED"


def test_a_cheaper_modification_shows_its_refund(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    student = _student(engine)
    order = _place(api, student, menu, THALI + TEA)
    assert _modify(api, student, order, _cart(menu, thali=1), THALI).status_code == 200

    [refund] = _detail(api, student, order["id"])["refunds"]

    assert (refund["amount_paise"], refund["cause"]) == (TEA, "MODIFY")


def test_my_orders_are_listed_newest_first_with_their_latest_price(
    api: TestClient, engine: Engine, menu: dict[str, Any], now: Clock
) -> None:
    student, other = _student(engine), _student(engine)
    first = _place(api, student, menu, THALI + TEA)
    now.now += timedelta(minutes=1)
    second = _place(api, student, menu, THALI + TEA)
    _place(api, other, menu, THALI + TEA)
    now.now += timedelta(minutes=1)
    assert _modify(api, student, first, _cart(menu, thali=2), 2 * THALI).status_code == 200

    response = api.get("/api/v1/orders", headers=_headers(student))

    assert response.status_code == 200
    listed = response.json()
    # Only the caller's own orders (FR-7).
    assert [order["id"] for order in listed] == [second["id"], first["id"]]
    # The modified order is listed at its latest snapshot.
    assert listed[1]["price"]["payable_paise"] == 2 * THALI


def test_the_list_is_limited(api: TestClient, engine: Engine, menu: dict[str, Any]) -> None:
    student = _student(engine)
    _place(api, student, menu, THALI + TEA)
    _place(api, student, menu, THALI + TEA)

    one = api.get("/api/v1/orders", params={"limit": 1}, headers=_headers(student))
    too_many = api.get("/api/v1/orders", params={"limit": 201}, headers=_headers(student))

    assert len(one.json()) == 1
    assert too_many.status_code == 422


def test_a_student_with_no_orders_gets_an_empty_list(api: TestClient, engine: Engine) -> None:
    response = api.get("/api/v1/orders", headers=_headers(_student(engine)))

    assert response.status_code == 200
    assert response.json() == []


def test_only_students_list_their_orders(api: TestClient, engine: Engine) -> None:
    for role in (Role.KITCHEN, Role.ADMIN):
        response = api.get("/api/v1/orders", headers=_headers(_student(engine, role)))
        assert response.status_code == 403
    assert api.get("/api/v1/orders").status_code == 401


def test_another_students_order_history_is_not_found(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    order = _place(api, _student(engine), menu, THALI + TEA)

    response = api.get(f"/api/v1/orders/{order['id']}", headers=_headers(_student(engine)))

    assert response.status_code == 404
    assert "snapshots" not in response.text
    assert uuid.UUID(order["id"])
