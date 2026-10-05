"""The core schema enforces its invariants in the database itself (NFR-2, FR-8)."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def conn(engine: Engine) -> Iterator[Connection]:
    """A connection whose changes are rolled back after each test."""
    with engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


def _add_item(conn: Connection, name: str = "Paneer Thali") -> str:
    return str(
        conn.execute(
            text(
                "INSERT INTO menu_items (name, category, price_paise) "
                "VALUES (:name, 'MEAL', 8000) RETURNING id"
            ),
            {"name": name},
        ).scalar_one()
    )


def _add_service_day(conn: Connection) -> None:
    conn.execute(
        text(
            "INSERT INTO service_days "
            "(service_date, window_start, window_end, slot_len_min, default_capacity) "
            "VALUES ('2026-10-06', '12:00', '14:30', 15, 30)"
        )
    )


def test_parameter_defaults_are_seeded(conn: Connection) -> None:
    value = conn.execute(text("SELECT value FROM settings WHERE key = 'P-MAX_QTY'")).scalar_one()
    assert value == 3


def test_inventory_cannot_be_over_allocated(conn: Connection) -> None:
    item_id = _add_item(conn)
    _add_service_day(conn)
    conn.execute(
        text(
            "INSERT INTO daily_inventory (item_id, service_date, total, allocated) "
            "VALUES (:item_id, '2026-10-06', 1, 1)"
        ),
        {"item_id": item_id},
    )
    with pytest.raises(IntegrityError, match="ck_daily_inventory_allocated_within_total"):
        conn.execute(text("UPDATE daily_inventory SET allocated = 2"))


def test_slot_cannot_be_overbooked(conn: Connection) -> None:
    _add_service_day(conn)
    conn.execute(
        text(
            "INSERT INTO slots (service_date, starts_at, ends_at, capacity, booked) "
            "VALUES ('2026-10-06', '2026-10-06 12:00+05:30', '2026-10-06 12:15+05:30', 30, 30)"
        )
    )
    with pytest.raises(IntegrityError, match="ck_slots_booked_within_capacity"):
        conn.execute(text("UPDATE slots SET booked = booked + 1"))


def test_active_item_names_are_unique(conn: Connection) -> None:
    _add_item(conn, "Paneer Thali")
    with pytest.raises(IntegrityError, match="uq_menu_items_active_name"):
        _add_item(conn, "paneer thali")


def test_removed_item_name_can_be_reused(conn: Connection) -> None:
    item_id = _add_item(conn, "Paneer Thali")
    conn.execute(text("UPDATE menu_items SET status = 'REMOVED' WHERE id = :id"), {"id": item_id})
    _add_item(conn, "Paneer Thali")
