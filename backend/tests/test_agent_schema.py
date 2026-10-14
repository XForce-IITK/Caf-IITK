"""The agent schema (SADD Figure 2.6) and the caf_agent role's privileges (NFR-25, FR-51).

Statements run under `SET LOCAL ROLE caf_agent`, so PostgreSQL itself decides what
the agent may do. The inventory UPDATE denial of US-41 AC3 is tested under
CAFIITK-166.
"""

import uuid
from collections.abc import Iterator

import pytest
from pydantic import ValidationError
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from app.models.enums import ProposalType
from app.modules.proposals.payloads import (
    DisablePayload,
    PrepPriorityPayload,
    ReplenishPayload,
    parse_payload,
)

SERVICE_DATE = "2026-10-06"


@pytest.fixture
def conn(engine: Engine) -> Iterator[Connection]:
    """A connection whose changes are rolled back after each test."""
    with engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


def _as_agent(conn: Connection) -> None:
    conn.execute(text("SET LOCAL ROLE caf_agent"))


def _add_order(conn: Connection, status: str = "ACCEPTED", qty: int = 2) -> dict[str, str]:
    """One student's order for one item in one slot; returns the IDs involved."""
    student_id = conn.execute(
        text(
            "INSERT INTO users (email, name, password_hash, role) "
            "VALUES (:email, 'Asha', 'x', 'STUDENT') RETURNING id"
        ),
        {"email": f"{uuid.uuid4().hex}@iitk.ac.in"},
    ).scalar_one()
    item_id = conn.execute(
        text(
            "INSERT INTO menu_items (name, category, price_paise) "
            "VALUES (:name, 'MEAL', 8000) RETURNING id"
        ),
        {"name": f"Thali {uuid.uuid4().hex[:8]}"},
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO service_days "
            "(service_date, window_start, window_end, slot_len_min, default_capacity) "
            "VALUES (:d, '12:00', '14:30', 15, 30) ON CONFLICT DO NOTHING"
        ),
        {"d": SERVICE_DATE},
    )
    slot_id = conn.execute(
        text(
            "INSERT INTO slots (service_date, starts_at, ends_at, capacity, booked) "
            "VALUES (:d, :start, :end, 30, 1) "
            "ON CONFLICT (service_date, starts_at) DO UPDATE SET booked = slots.booked + 1 "
            "RETURNING id"
        ),
        {
            "d": SERVICE_DATE,
            "start": f"{SERVICE_DATE} 12:00+05:30",
            "end": f"{SERVICE_DATE} 12:15+05:30",
        },
    ).scalar_one()
    order_id = conn.execute(
        text(
            "INSERT INTO orders (student_id, slot_id, status) "
            "VALUES (:student, :slot, :status) RETURNING id"
        ),
        {"student": student_id, "slot": slot_id, "status": status},
    ).scalar_one()
    conn.execute(
        text("INSERT INTO order_lines (order_id, item_id, qty) VALUES (:o, :i, :q)"),
        {"o": order_id, "i": item_id, "q": qty},
    )
    return {"student_id": str(student_id), "item_id": str(item_id), "slot_id": str(slot_id)}


def _add_run(conn: Connection, status: str = "RUNNING") -> str:
    return str(
        conn.execute(
            text("INSERT INTO agent_runs (trigger, status) VALUES ('ON_DEMAND', :s) RETURNING id"),
            {"s": status},
        ).scalar_one()
    )


def test_agent_reads_demand_through_its_views(conn: Connection) -> None:
    ids = _add_order(conn, qty=2)
    _add_order(conn, status="CANCELLED", qty=5)  # not pending, so not counted
    _as_agent(conn)

    row = (
        conn.execute(
            text("SELECT * FROM agent_pending_demand WHERE item_id = :i"), {"i": ids["item_id"]}
        )
        .mappings()
        .one()
    )

    assert row["portions"] == 2
    assert row["orders"] == 1
    assert str(row["slot_id"]) == ids["slot_id"]


@pytest.mark.parametrize(
    "view",
    [
        "agent_pending_demand",
        "agent_inventory_levels",
        "agent_slot_utilisation",
        "agent_historical_demand",
        "agent_menu_config",
    ],
)
def test_views_expose_no_student_identifiers(conn: Connection, view: str) -> None:
    _as_agent(conn)
    columns = set(conn.execute(text(f"SELECT * FROM {view} LIMIT 0")).keys())

    assert columns.isdisjoint({"student_id", "user_id", "email", "name_of_student"})


@pytest.mark.parametrize("table", ["orders", "users", "order_lines", "daily_inventory"])
def test_agent_cannot_read_tables_directly(conn: Connection, table: str) -> None:
    _as_agent(conn)

    with pytest.raises(ProgrammingError, match="permission denied"):
        conn.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))


def test_agent_can_insert_a_proposal(conn: Connection) -> None:
    run_id = _add_run(conn)
    proposal_id = uuid.uuid4()
    _as_agent(conn)

    # No RETURNING: that would need SELECT on proposals, which caf_agent lacks.
    conn.execute(
        text(
            "INSERT INTO proposals (id, run_id, type, target_date, payload, rationale, "
            "source, expires_at) VALUES (:id, :run, 'DISABLE', :d, '{}', 'low stock', "
            "'HEURISTIC', now())"
        ),
        {"id": proposal_id, "run": run_id, "d": SERVICE_DATE},
    )
    conn.execute(text("RESET ROLE"))

    status = conn.execute(
        text("SELECT status FROM proposals WHERE id = :id"), {"id": proposal_id}
    ).scalar_one()
    assert status == "PENDING"


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE proposals SET status = 'APPROVED'",
        "DELETE FROM proposals",
        "UPDATE agent_runs SET status = 'SUCCEEDED'",
        "INSERT INTO agent_runs (trigger, status) VALUES ('ON_DEMAND', 'RUNNING')",
    ],
)
def test_agent_cannot_decide_proposals_or_manage_runs(conn: Connection, statement: str) -> None:
    _as_agent(conn)

    with pytest.raises(ProgrammingError, match="permission denied"):
        conn.execute(text(statement))


def test_agent_can_log_tool_and_llm_calls(conn: Connection) -> None:
    run_id = _add_run(conn)
    _as_agent(conn)

    conn.execute(
        text(
            "INSERT INTO agent_tool_calls (run_id, seq, tool, args, outcome) "
            "VALUES (:run, 1, 'get_inventory_levels', '{}', 'OK')"
        ),
        {"run": run_id},
    )
    conn.execute(
        text("INSERT INTO agent_llm_calls (run_id, model, outcome) VALUES (:run, 'stub', 'OK')"),
        {"run": run_id},
    )


def test_only_one_run_can_be_in_progress(conn: Connection) -> None:
    _add_run(conn, status="RUNNING")

    with pytest.raises(IntegrityError, match="uq_agent_runs_one_active"):
        _add_run(conn, status="QUEUED")


def test_finished_runs_do_not_block_a_new_one(conn: Connection) -> None:
    _add_run(conn, status="SUCCEEDED")
    _add_run(conn, status="FAILED")

    _add_run(conn, status="RUNNING")


def test_payload_shapes_parse_by_type() -> None:
    item = uuid.uuid4()

    disable = parse_payload(ProposalType.DISABLE, {"item_id": str(item), "reason": "low stock"})
    prep = parse_payload(ProposalType.PREP_PRIORITY, {"item_ids": [str(item)]})
    replenish = parse_payload(
        ProposalType.REPLENISH, {"lines": [{"item_id": str(item), "additional_portions": 20}]}
    )

    assert disable == DisablePayload(item_id=item, reason="low stock")
    assert prep == PrepPriorityPayload(item_ids=[item])
    assert isinstance(replenish, ReplenishPayload)
    assert replenish.lines[0].additional_portions == 20


@pytest.mark.parametrize(
    ("proposal_type", "payload"),
    [
        (ProposalType.DISABLE, {"item_id": "not-a-uuid", "reason": "x"}),
        (ProposalType.DISABLE, {"item_id": str(uuid.uuid4()), "reason": " "}),
        (ProposalType.PREP_PRIORITY, {"item_ids": []}),
        (ProposalType.PREP_PRIORITY, {"item_ids": [str(uuid.UUID(int=1))] * 2}),
        (
            ProposalType.REPLENISH,
            {"lines": [{"item_id": str(uuid.uuid4()), "additional_portions": 0}]},
        ),
        (
            ProposalType.REPLENISH,
            {"lines": [{"item_id": str(uuid.UUID(int=1)), "additional_portions": 5}] * 2},
        ),
        (ProposalType.DISABLE, {"item_id": str(uuid.uuid4()), "reason": "x", "extra": 1}),
    ],
)
def test_malformed_payloads_are_rejected(proposal_type: ProposalType, payload: object) -> None:
    with pytest.raises(ValidationError):
        parse_payload(proposal_type, payload)
