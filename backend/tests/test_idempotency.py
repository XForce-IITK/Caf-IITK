"""US-25 (CAFIITK-150; FR-32, NFR-7) acceptance tests TC-US25-AC1..AC3.

POST /orders is CAFIITK-147 (not built yet), so these tests use a stand-in order
endpoint that follows the contract 147 must use: claim the key, allocate portions
and a seat, create the order and store the result, all in one transaction. When
147 lands, its own tests should repeat AC1-AC3 against the real endpoint.
"""

import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any
from zoneinfo import ZoneInfo

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import Engine, func, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import create_access_token
from app.db.session import get_session
from app.models.capacity import DailyInventory, ServiceDay, Slot
from app.models.catalogue import MenuItem
from app.models.enums import IdempotencyState, ItemCategory, OrderStatus, Role
from app.models.identity import User
from app.models.ordering import IdempotencyKey, Order, OrderLine
from app.modules.identity.dependencies import require_permission
from app.modules.identity.permissions import Permission
from app.modules.ordering.idempotency import (
    IdempotencyKeyHeader,
    IdempotencyKeyReusedError,
    IdempotencyService,
    RequestInProgressError,
    request_hash,
)

IST = ZoneInfo("Asia/Kolkata")
D = date(2026, 10, 6)


class Line(BaseModel):
    item_id: uuid.UUID
    qty: int


class OrderIn(BaseModel):
    slot_id: uuid.UUID
    lines: list[Line]


def _stand_in_app() -> FastAPI:
    app = FastAPI()

    @app.post("/orders", status_code=201)
    def place_order(
        body: OrderIn,
        key: IdempotencyKeyHeader,
        student: Annotated[User, Depends(require_permission(Permission.MANAGE_OWN_ORDERS))],
        session: Annotated[Session, Depends(get_session)],
    ) -> Any:
        idempotency = IdempotencyService(session)
        try:
            with session.begin():
                replay = idempotency.claim(student.id, key, body.model_dump(mode="json"))
                if replay is not None:
                    return JSONResponse(replay.response, status_code=201)
                for line in body.lines:
                    session.execute(
                        update(DailyInventory)
                        .where(DailyInventory.item_id == line.item_id)
                        .values(allocated=DailyInventory.allocated + line.qty)
                    )
                session.execute(
                    update(Slot).where(Slot.id == body.slot_id).values(booked=Slot.booked + 1)
                )
                order = Order(
                    student_id=student.id, slot_id=body.slot_id, status=OrderStatus.ACCEPTED
                )
                session.add(order)
                session.flush()
                session.add_all(
                    OrderLine(order_id=order.id, item_id=line.item_id, qty=line.qty)
                    for line in body.lines
                )
                result = {"order_id": str(order.id), "status": "ACCEPTED"}
                idempotency.complete(student.id, key, result)
                return result
        except IdempotencyKeyReusedError:
            raise HTTPException(
                422, "Idempotency-Key was already used with a different request"
            ) from None
        except RequestInProgressError:
            raise HTTPException(
                409, "A request with this Idempotency-Key is still in progress"
            ) from None

    return app


@pytest.fixture
def api(engine: Engine) -> Iterator[TestClient]:
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def test_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    app = _stand_in_app()
    app.dependency_overrides[get_session] = test_session
    yield TestClient(app)
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE users, menu_items, service_days CASCADE"))


def _student(engine: Engine) -> User:
    with Session(engine, expire_on_commit=False) as session, session.begin():
        user = User(
            id=uuid.uuid4(),
            name="Asha",
            email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
            password_hash="unused",
            role=Role.STUDENT,
        )
        session.add(user)
    return user


def _auth(user: User, key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_access_token(user.id, user.role)}",
        "Idempotency-Key": key,
    }


@pytest.fixture
def menu(engine: Engine) -> dict[str, Any]:
    with Session(engine, expire_on_commit=False) as session, session.begin():
        thali = MenuItem(name="Thali", category=ItemCategory.MEAL, price_paise=8000)
        tea = MenuItem(name="Tea", category=ItemCategory.BEVERAGE, price_paise=1500)
        session.add_all(
            [
                thali,
                tea,
                ServiceDay(
                    service_date=D,
                    window_start=time(12, 0),
                    window_end=time(12, 15),
                    slot_len_min=15,
                    default_capacity=30,
                ),
            ]
        )
        session.flush()
        slot = Slot(
            service_date=D,
            starts_at=datetime(2026, 10, 6, 12, 0, tzinfo=IST),
            ends_at=datetime(2026, 10, 6, 12, 15, tzinfo=IST),
            capacity=30,
        )
        session.add_all(
            [
                slot,
                DailyInventory(item_id=thali.id, service_date=D, total=50),
                DailyInventory(item_id=tea.id, service_date=D, total=50),
            ]
        )
    return {"thali": thali.id, "tea": tea.id, "slot": slot.id}


def _cart(menu: dict[str, Any], thali_qty: int = 2) -> dict[str, Any]:
    return {
        "slot_id": str(menu["slot"]),
        "lines": [{"item_id": str(menu["thali"]), "qty": thali_qty}],
    }


def _counts(engine: Engine, menu: dict[str, Any]) -> tuple[int, int, int]:
    with Session(engine) as session:
        allocated = session.scalar(
            select(DailyInventory.allocated).where(DailyInventory.item_id == menu["thali"])
        )
        booked = session.scalar(select(Slot.booked).where(Slot.id == menu["slot"]))
        orders = session.scalar(select(func.count()).select_from(Order))
    assert allocated is not None and booked is not None and orders is not None
    return allocated, booked, orders


def test_tc_us25_ac1_repeat_returns_the_original_order_and_allocates_once(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    student = _student(engine)
    headers = _auth(student, "key-1")

    first = api.post("/orders", json=_cart(menu), headers=headers)
    again = api.post("/orders", json=_cart(menu), headers=headers)

    assert first.status_code == again.status_code == 201
    assert again.json() == first.json()
    assert _counts(engine, menu) == (2, 1, 1)  # 2 portions, 1 seat, 1 order


def test_payload_key_order_does_not_matter(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    student = _student(engine)
    cart = _cart(menu)
    reordered = {"lines": cart["lines"], "slot_id": cart["slot_id"]}

    first = api.post("/orders", json=cart, headers=_auth(student, "k"))
    again = api.post("/orders", json=reordered, headers=_auth(student, "k"))

    assert again.json() == first.json()
    assert _counts(engine, menu)[2] == 1


def test_tc_us25_ac2_same_key_different_cart_is_422(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    student = _student(engine)
    assert api.post("/orders", json=_cart(menu), headers=_auth(student, "k")).status_code == 201

    response = api.post("/orders", json=_cart(menu, thali_qty=3), headers=_auth(student, "k"))

    assert response.status_code == 422
    assert _counts(engine, menu) == (2, 1, 1)


def test_tc_us25_ac3_twenty_concurrent_duplicates_create_one_order(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    student = _student(engine)
    headers = _auth(student, "burst")

    with ThreadPoolExecutor(max_workers=20) as pool:
        responses = list(
            pool.map(lambda _: api.post("/orders", json=_cart(menu), headers=headers), range(20))
        )

    assert {r.status_code for r in responses} == {201}
    assert len({r.json()["order_id"] for r in responses}) == 1
    assert _counts(engine, menu) == (2, 1, 1)


def test_keys_are_scoped_to_the_student(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    a, b = _student(engine), _student(engine)

    first = api.post("/orders", json=_cart(menu), headers=_auth(a, "shared"))
    second = api.post("/orders", json=_cart(menu, thali_qty=1), headers=_auth(b, "shared"))

    assert first.status_code == second.status_code == 201
    assert first.json()["order_id"] != second.json()["order_id"]
    assert _counts(engine, menu) == (3, 2, 2)


def test_a_new_key_is_a_new_order(api: TestClient, engine: Engine, menu: dict[str, Any]) -> None:
    student = _student(engine)
    api.post("/orders", json=_cart(menu), headers=_auth(student, "k1"))
    api.post("/orders", json=_cart(menu), headers=_auth(student, "k2"))
    assert _counts(engine, menu) == (4, 2, 2)


def test_key_older_than_p_idem_ttl_can_be_reused(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    student = _student(engine)
    api.post("/orders", json=_cart(menu), headers=_auth(student, "old"))
    with Session(engine) as session, session.begin():
        session.execute(
            update(IdempotencyKey).values(created_at=datetime.now(UTC) - timedelta(hours=25))
        )

    # A different cart is accepted because the old key has expired.
    response = api.post("/orders", json=_cart(menu, thali_qty=1), headers=_auth(student, "old"))

    assert response.status_code == 201
    assert _counts(engine, menu) == (3, 2, 2)


def test_unfinished_original_request_gives_409(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    # e.g. the order committed but payment confirmation (a later transaction) is pending.
    student = _student(engine)
    with Session(engine) as session, session.begin():
        session.add(
            IdempotencyKey(
                user_id=student.id,
                key="pending",
                request_hash=request_hash(_cart(menu)),
                state=IdempotencyState.IN_PROGRESS,
            )
        )

    response = api.post("/orders", json=_cart(menu), headers=_auth(student, "pending"))

    assert response.status_code == 409
    assert _counts(engine, menu) == (0, 0, 0)


def test_failed_request_releases_the_key(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    student = _student(engine)
    bad = {"slot_id": str(menu["slot"]), "lines": [{"item_id": str(uuid.uuid4()), "qty": 1}]}

    # Unknown item: the order_lines foreign key fails and the whole transaction rolls back.
    with pytest.raises(Exception):  # noqa: B017
        api.post("/orders", json=bad, headers=_auth(student, "retry-me"))

    with Session(engine) as session:
        assert session.get(IdempotencyKey, (student.id, "retry-me")) is None
    # The key was not consumed, so a corrected retry with the same key succeeds.
    assert (
        api.post("/orders", json=_cart(menu), headers=_auth(student, "retry-me")).status_code == 201
    )


@pytest.mark.parametrize("key", [None, "", "x" * 101, "has space", "semi;colon"])
def test_missing_or_malformed_key_is_422(
    api: TestClient, engine: Engine, menu: dict[str, Any], key: str | None
) -> None:
    student = _student(engine)
    headers = {"Authorization": f"Bearer {create_access_token(student.id, student.role)}"}
    if key is not None:
        headers["Idempotency-Key"] = key

    assert api.post("/orders", json=_cart(menu), headers=headers).status_code == 422
    assert _counts(engine, menu) == (0, 0, 0)


def test_request_hash_ignores_key_order_and_whitespace() -> None:
    assert request_hash({"a": 1, "b": [1, 2]}) == request_hash({"b": [1, 2], "a": 1})
    assert request_hash({"a": 1}) != request_hash({"a": 2})
