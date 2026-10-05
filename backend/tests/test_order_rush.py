"""US-30 (NFR-1, NFR-2, NFR-4, NFR-5, NFR-13) acceptance tests TC-US30-AC1..AC4.

AC3 and AC4 exercise modify and cancel, which arrive in Sprint 2; they are
skipped here so the gap stays visible in every test report.
"""

import uuid
from collections.abc import Iterator
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import loadgen
import pytest
from conftest import LiveStack
from sqlalchemy import Engine, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.capacity import DailyInventory, ServiceDay, Slot
from app.models.catalogue import MenuItem
from app.models.enums import ItemCategory

IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 10, 6)


@pytest.fixture
def clean_db(engine: Engine) -> Iterator[Engine]:
    yield engine
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE users, menu_items, service_days, discount_rules CASCADE"))


def test_tc_us30_ac1_two_hundred_concurrent_orders_never_oversell(
    live_stack: LiveStack, clean_db: Engine
) -> None:
    """NFR-1 and NFR-13: 50 portions, 30 seats, two API processes, 10 consecutive runs."""
    reports = loadgen.run_rush(
        live_stack.api_urls, clean_db, requests=200, portions=50, seats=30, runs=10
    )

    assert len(reports) == 10
    for number, report in enumerate(reports, start=1):
        assert report.ok, f"run {number}: {report.summary()}"
        assert (report.accepted, report.rejected) == (30, 170)
        assert report.statuses == {201: 30, 409: 170}
        assert (report.available_portions, report.remaining_seats) == (20, 0)


@pytest.fixture
def sold_out(clean_db: Engine) -> dict[str, Any]:
    """One item with no portion left and one slot with no seat left."""
    thali = MenuItem(id=uuid.uuid4(), name="Thali", category=ItemCategory.MEAL, price_paise=8000)
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
        booked=30,
    )
    with Session(clean_db, expire_on_commit=False) as session, session.begin():
        session.add_all([thali, day])
        session.flush()
        session.add_all(
            [slot, DailyInventory(item_id=thali.id, service_date=DAY, total=50, allocated=50)]
        )
    return {"thali": thali, "slot": slot}


# What application code with a broken availability check would attempt.
BYPASSES = {
    "one more portion than exists": lambda ids: (
        update(DailyInventory)
        .where(DailyInventory.item_id == ids["thali"].id)
        .values(allocated=DailyInventory.allocated + 1)
    ),
    "release more portions than were allocated": lambda ids: (
        update(DailyInventory).where(DailyInventory.item_id == ids["thali"].id).values(allocated=-1)
    ),
    "shrink the total below what is allocated": lambda ids: (
        update(DailyInventory).where(DailyInventory.item_id == ids["thali"].id).values(total=49)
    ),
    "one more seat than exists": lambda ids: (
        update(Slot).where(Slot.id == ids["slot"].id).values(booked=Slot.booked + 1)
    ),
    "release more seats than were booked": lambda ids: (
        update(Slot).where(Slot.id == ids["slot"].id).values(booked=-1)
    ),
}


@pytest.mark.parametrize("bypass", BYPASSES)
def test_tc_us30_ac2_database_refuses_a_count_the_application_should_never_write(
    clean_db: Engine, sold_out: dict[str, Any], bypass: str
) -> None:
    """NFR-2: the CHECK constraints hold even when the application's own check is skipped."""
    with (
        pytest.raises(IntegrityError, match="allocated_within_total|booked_within_capacity"),
        Session(clean_db) as session,
        session.begin(),
    ):
        session.execute(BYPASSES[bypass](sold_out))

    with Session(clean_db) as session:
        stock = session.get(DailyInventory, (sold_out["thali"].id, DAY))
        slot = session.get(Slot, sold_out["slot"].id)
        assert stock is not None and slot is not None
        assert (stock.total, stock.allocated, slot.booked) == (50, 50, 30)


@pytest.mark.skip(reason="needs the modify and cancel endpoints (Sprint 2)")
def test_tc_us30_ac3_concurrent_modify_and_cancel_exactly_one_succeeds() -> None:
    """NFR-5: one ACCEPTED order, a modify and a cancel together; one wins, the other gets 409."""


@pytest.mark.skip(reason="needs the modify and cancel endpoints (Sprint 2)")
def test_tc_us30_ac4_mixed_workload_has_no_unhandled_deadlock() -> None:
    """NFR-4: 60 seconds of mixed create, modify and cancel without an unhandled deadlock."""
