"""US-35: preparation starts automatically at slot start - P-AUTO_PREP (FR-44, T5)."""

import uuid
from collections.abc import Iterator
from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app.core import clock
from app.models.capacity import ServiceDay, Slot
from app.models.enums import OrderStatus, Role
from app.models.identity import User
from app.models.ordering import Order, OrderTransition
from app.modules.ordering.auto_prep import AUTO_PREP_REASON, AutoPrepService, _NoPayments
from app.worker.jobs import all_jobs

IST = clock.IST
DAY = date(2026, 11, 21)


def _at(hour: int, minute: int) -> datetime:
    return datetime.combine(DAY, time(hour, minute), tzinfo=IST)


class Day:
    """Slots at 12:30 and 13:00, and one Student's orders in them."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.student = User(
            id=uuid.uuid4(),
            name="Asha",
            email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
            password_hash="unused",
            role=Role.STUDENT,
        )
        self.half_past, self.one = (
            Slot(
                id=uuid.uuid4(),
                service_date=DAY,
                starts_at=start,
                ends_at=start + timedelta(minutes=30),
                capacity=30,
                booked=0,
            )
            for start in (_at(12, 30), _at(13, 0))
        )
        with Session(engine, expire_on_commit=False) as session, session.begin():
            session.add(self.student)
            session.add(
                ServiceDay(
                    service_date=DAY,
                    window_start=time(12, 30),
                    window_end=time(13, 30),
                    slot_len_min=30,
                    default_capacity=30,
                )
            )
            session.flush()
            session.add_all([self.half_past, self.one])

    def order(self, slot: Slot, status: OrderStatus = OrderStatus.ACCEPTED) -> uuid.UUID:
        order = Order(id=uuid.uuid4(), student_id=self.student.id, slot_id=slot.id, status=status)
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            session.add(order)
        return order.id

    def status(self, order_id: uuid.UUID) -> tuple[OrderStatus, int]:
        with Session(self.engine) as session:
            order = session.get(Order, order_id)
            assert order is not None
            return order.status, order.version


@pytest.fixture
def day(engine: Engine, db_client: TestClient) -> Iterator[Day]:
    # db_client truncates users and service days (and so orders and slots) afterwards.
    yield Day(engine)


def _start_due(engine: Engine, now: datetime) -> int:
    with Session(engine, expire_on_commit=False) as session:
        return AutoPrepService(session).start_due(now)


def test_tc_us35_ac1_accepted_orders_start_at_slot_start_minus_p_auto_prep(
    day: Day, engine: Engine
) -> None:
    first, second = day.order(day.half_past), day.order(day.half_past)
    later = day.order(day.one)

    assert _start_due(engine, _at(12, 19)) == 0  # P-AUTO_PREP is 10 minutes
    assert _start_due(engine, _at(12, 20)) == 2

    assert day.status(first)[0] is OrderStatus.PREPARING
    assert day.status(second)[0] is OrderStatus.PREPARING
    assert day.status(later)[0] is OrderStatus.ACCEPTED
    with Session(engine) as session:
        transition = session.scalars(
            select(OrderTransition).where(OrderTransition.order_id == first)
        ).one()
        audit = (
            session.execute(
                text(
                    "SELECT actor_id, actor_role, before, after FROM audit_log "
                    "WHERE action = 'ORDER_TRANSITION' AND entity_id = :id"
                ),
                {"id": str(first)},
            )
            .mappings()
            .one()
        )
    assert (transition.from_status, transition.to_status) == (
        OrderStatus.ACCEPTED,
        OrderStatus.PREPARING,
    )
    assert transition.actor_id is None
    assert transition.reason == AUTO_PREP_REASON
    assert audit["actor_role"] == "SYSTEM"
    assert audit["actor_id"] is None
    assert audit["before"] == {"status": "ACCEPTED"}
    assert audit["after"]["status"] == "PREPARING"


def test_only_accepted_orders_move(day: Day, engine: Engine) -> None:
    others = {
        status: day.order(day.half_past, status)
        for status in (
            OrderStatus.PENDING_PAYMENT,
            OrderStatus.PREPARING,
            OrderStatus.READY,
            OrderStatus.CANCELLED,
            OrderStatus.PAYMENT_FAILED,
        )
    }

    assert _start_due(engine, _at(12, 25)) == 0
    for status, order_id in others.items():
        assert day.status(order_id)[0] is status


def test_running_again_moves_nothing_more(day: Day, engine: Engine) -> None:
    day.order(day.half_past)

    assert _start_due(engine, _at(12, 20)) == 1
    assert _start_due(engine, _at(12, 21)) == 0


def test_a_late_run_still_starts_orders_whose_slot_has_begun(day: Day, engine: Engine) -> None:
    order_id = day.order(day.half_past)

    assert _start_due(engine, _at(12, 45)) == 1  # e.g. the worker was restarting at 12:20
    assert day.status(order_id)[0] is OrderStatus.PREPARING


def test_starting_bumps_the_version_so_a_stale_student_action_is_refused(
    day: Day, engine: Engine
) -> None:
    order_id = day.order(day.half_past)
    _, version_before = day.status(order_id)

    _start_due(engine, _at(12, 20))

    assert day.status(order_id)[1] == version_before + 1


def test_an_order_changed_after_it_was_found_is_skipped(day: Day, engine: Engine) -> None:
    order_id = day.order(day.half_past)
    with Session(engine, expire_on_commit=False) as session:
        service = AutoPrepService(session)
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE orders SET status = 'CANCELLED' WHERE id = :id"), {"id": order_id}
            )
        with session.begin():
            assert service._start(order_id) is False

    assert day.status(order_id)[0] is OrderStatus.CANCELLED


def test_auto_prep_never_touches_payments() -> None:
    gateway = _NoPayments()
    for call in (
        lambda: gateway.authorise("r", 1),
        lambda: gateway.void("r"),
        lambda: gateway.refund("r", "a", 1),
    ):
        with pytest.raises(RuntimeError, match="must not"):
            call()


def test_the_worker_runs_auto_prep(
    configured_database: None, day: Day, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.ordering import jobs

    assert "auto-prep" in {job.name for job in all_jobs()}
    order_id = day.order(day.half_past)
    monkeypatch.setattr(jobs.clock, "now", lambda: _at(12, 20))

    jobs.auto_start_preparation()

    assert day.status(order_id)[0] is OrderStatus.PREPARING
