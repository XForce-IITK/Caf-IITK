"""CAFIITK-210: READY orders nobody collected become NO_SHOW at the end of the service day.

The day's last slot end + P-NOSHOW_GRACE closes them with actor SYSTEM (T11): no
refund, and neither portions nor seat come back.
"""

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
from app.modules.ordering.auto_noshow import AUTO_NO_SHOW_REASON, AutoNoShowService
from app.worker.jobs import all_jobs

IST = clock.IST
DAY = date(2026, 11, 21)
NEXT_DAY = DAY + timedelta(days=1)


def _at(hour: int, minute: int, day: date = DAY) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=IST)


class Day:
    """Slots at 12:30 and 13:00 (the day ends 13:30), one at 12:30 the next day,
    and one Student's orders in them."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.student = User(
            id=uuid.uuid4(),
            name="Asha",
            email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
            password_hash="unused",
            role=Role.STUDENT,
        )
        self.half_past, self.one, self.tomorrow = (
            Slot(
                id=uuid.uuid4(),
                service_date=start.date(),
                starts_at=start,
                ends_at=start + timedelta(minutes=30),
                capacity=30,
                booked=1,
            )
            for start in (_at(12, 30), _at(13, 0), _at(12, 30, NEXT_DAY))
        )
        with Session(engine, expire_on_commit=False) as session, session.begin():
            session.add(self.student)
            for service_date in (DAY, NEXT_DAY):
                session.add(
                    ServiceDay(
                        service_date=service_date,
                        window_start=time(12, 30),
                        window_end=time(13, 30),
                        slot_len_min=30,
                        default_capacity=30,
                    )
                )
            session.flush()
            session.add_all([self.half_past, self.one, self.tomorrow])

    def order(self, slot: Slot, status: OrderStatus = OrderStatus.READY) -> uuid.UUID:
        order = Order(id=uuid.uuid4(), student_id=self.student.id, slot_id=slot.id, status=status)
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            session.add(order)
        return order.id

    def status(self, order_id: uuid.UUID) -> tuple[OrderStatus, int]:
        with Session(self.engine) as session:
            order = session.get(Order, order_id)
            assert order is not None
            return order.status, order.version

    def booked(self, slot: Slot) -> int:
        with Session(self.engine) as session:
            row = session.get(Slot, slot.id)
            assert row is not None
            return row.booked


@pytest.fixture
def day(engine: Engine, db_client: TestClient) -> Iterator[Day]:
    # db_client truncates users and service days (and so orders and slots) afterwards.
    yield Day(engine)


def _close(engine: Engine, now: datetime) -> int:
    with Session(engine, expire_on_commit=False) as session:
        return AutoNoShowService(session).close_uncollected(now)


def test_ready_orders_close_at_day_end_plus_p_noshow_grace(day: Day, engine: Engine) -> None:
    early, late = day.order(day.half_past), day.order(day.one)

    # The 12:30 slot's own no-show time (13:15) has passed, but service is still on.
    assert _close(engine, _at(13, 20)) == 0
    assert _close(engine, _at(13, 44)) == 0  # P-NOSHOW_GRACE is 15 minutes after 13:30
    assert _close(engine, _at(13, 45)) == 2

    assert day.status(early)[0] is OrderStatus.NO_SHOW
    assert day.status(late)[0] is OrderStatus.NO_SHOW
    with Session(engine) as session:
        transition = session.scalars(
            select(OrderTransition).where(OrderTransition.order_id == early)
        ).one()
        audit = (
            session.execute(
                text(
                    "SELECT actor_id, actor_role, before, after FROM audit_log "
                    "WHERE action = 'ORDER_TRANSITION' AND entity_id = :id"
                ),
                {"id": str(early)},
            )
            .mappings()
            .one()
        )
    assert (transition.from_status, transition.to_status) == (
        OrderStatus.READY,
        OrderStatus.NO_SHOW,
    )
    assert transition.actor_id is None
    assert transition.reason == AUTO_NO_SHOW_REASON
    assert audit["actor_role"] == "SYSTEM"
    assert audit["actor_id"] is None
    assert audit["before"] == {"status": "READY"}
    assert audit["after"]["status"] == "NO_SHOW"


def test_a_no_show_restores_nothing_and_refunds_nothing(day: Day, engine: Engine) -> None:
    order_id = day.order(day.half_past)

    assert _close(engine, _at(13, 45)) == 1

    assert day.booked(day.half_past) == 1  # the seat stays consumed
    with Session(engine) as session:
        released = session.execute(
            text(
                "SELECT count(*) FROM audit_log WHERE action IN "
                "('PORTIONS_RELEASED', 'SEAT_RELEASED') AND after::text LIKE '%' || :id || '%'"
            ),
            {"id": str(order_id)},
        ).scalar_one()
        payments = session.execute(
            text("SELECT count(*) FROM payments WHERE order_id = :id"), {"id": order_id}
        ).scalar_one()
    assert released == 0
    assert payments == 0


def test_only_ready_orders_of_finished_days_move(day: Day, engine: Engine) -> None:
    others = {
        status: day.order(day.half_past, status)
        for status in (
            OrderStatus.PENDING_PAYMENT,
            OrderStatus.ACCEPTED,
            OrderStatus.PREPARING,
            OrderStatus.PICKED_UP,
            OrderStatus.CANCELLED,
            OrderStatus.PAYMENT_FAILED,
        )
    }
    tomorrow = day.order(day.tomorrow)

    assert _close(engine, _at(13, 45)) == 0
    for status, order_id in others.items():
        assert day.status(order_id)[0] is status
    assert day.status(tomorrow)[0] is OrderStatus.READY


def test_running_again_moves_nothing_more(day: Day, engine: Engine) -> None:
    order_id = day.order(day.half_past)

    assert _close(engine, _at(13, 45)) == 1
    _, version = day.status(order_id)
    assert _close(engine, _at(13, 46)) == 0
    assert day.status(order_id) == (OrderStatus.NO_SHOW, version)


def test_a_late_run_still_closes_earlier_days(day: Day, engine: Engine) -> None:
    order_id = day.order(day.half_past)

    assert _close(engine, _at(9, 0, NEXT_DAY)) == 1  # e.g. the worker was down overnight
    assert day.status(order_id)[0] is OrderStatus.NO_SHOW


def test_an_order_picked_up_after_it_was_found_is_skipped(day: Day, engine: Engine) -> None:
    order_id = day.order(day.half_past)
    with Session(engine, expire_on_commit=False) as session:
        service = AutoNoShowService(session)
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE orders SET status = 'PICKED_UP' WHERE id = :id"), {"id": order_id}
            )
        with session.begin():
            assert service._close(order_id) is False

    assert day.status(order_id)[0] is OrderStatus.PICKED_UP


def test_the_worker_runs_auto_no_show(
    configured_database: None, day: Day, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.ordering import jobs

    assert "auto-no-show" in {job.name for job in all_jobs()}
    order_id = day.order(day.half_past)
    monkeypatch.setattr(jobs.clock, "now", lambda: _at(13, 45))

    jobs.close_uncollected_orders()

    assert day.status(order_id)[0] is OrderStatus.NO_SHOW
