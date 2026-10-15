"""US-39: the planning agent run (FR-50 - FR-52, FR-62), against real PostgreSQL.

The LLM is the scripted StubProvider behind the real GuardedLLMClient, so every
guard runs; only the provider is fake. Data reads, logs and proposals go through
the caf_agent role exactly as in production.
"""

import json
import re
import threading
import time as time_module
import uuid
from collections.abc import Callable, Iterator
from datetime import date, datetime, time, timedelta
from typing import Any

import httpx
import openai
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core import clock
from app.core.security import create_access_token
from app.models.agent import AgentRun
from app.models.capacity import DailyInventory, ServiceDay, Slot
from app.models.catalogue import MenuItem
from app.models.enums import (
    AgentRunStatus,
    AgentTrigger,
    ItemCategory,
    OrderStatus,
    ProposalType,
    Role,
)
from app.models.identity import User
from app.models.ordering import Order, OrderLine
from app.modules.agent import heuristic
from app.modules.agent.forecast import Risk, Snapshot, build_report, forecast
from app.modules.agent.llm import (
    DAILY_BUDGET_SUBJECT,
    CircuitBreaker,
    GuardedLLMClient,
    LLMResponse,
    ResponseCache,
    ToolCall,
)
from app.modules.agent.openai_provider import OpenAIProvider
from app.modules.agent.orchestrator import PlanningOrchestrator, RunLimits
from app.modules.agent.service import AgentService
from app.modules.agent.stub import StubProvider, reply
from app.modules.agent.tools import ToolRegistry
from app.modules.agent.validator import OutputValidator, ProposalRejectedError
from app.modules.proposals.payloads import parse_payload
from app.worker.jobs import all_jobs

IST = clock.IST
DAY = date(2026, 11, 20)
YESTERDAY = DAY - timedelta(days=1)
STUDENT_NAME = "Zebediah Quux"
STUDENT_EMAIL = "zebediah.quux@iitk.ac.in"
LIMITS = RunLimits(max_calls=20, timeout_s=30)


def _at(hour: int, minute: int, day: date = DAY) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=IST)


def _call(name: str, args: object = None, call_id: str | None = None) -> ToolCall:
    arguments = args if isinstance(args, str) else json.dumps(args or {})
    return ToolCall(call_id or f"call_{uuid.uuid4().hex[:6]}", name, arguments)


def _tools(*calls: ToolCall) -> LLMResponse:
    return reply(None, tool_calls=calls)


# --- Fixtures -------------------------------------------------------------------


class Kitchen:
    """A service day 12:00-13:00 with four 15-minute slots, two items and history."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.student = User(
            id=uuid.uuid4(),
            name=STUDENT_NAME,
            email=STUDENT_EMAIL,
            password_hash="unused",
            role=Role.STUDENT,
        )
        self.admin = User(
            id=uuid.uuid4(),
            name="Admin",
            email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
            password_hash="unused",
            role=Role.ADMIN,
        )
        self.thali = MenuItem(
            id=uuid.uuid4(), name="Paneer Thali", category=ItemCategory.MEAL, price_paise=8000
        )
        self.dosa = MenuItem(
            id=uuid.uuid4(), name="Masala Dosa", category=ItemCategory.MEAL, price_paise=5000
        )
        self.slots = [
            Slot(
                id=uuid.uuid4(),
                service_date=DAY,
                starts_at=_at(12, 15 * i),
                ends_at=_at(12, 15 * i) + timedelta(minutes=15),
                capacity=30,
                booked=0,
            )
            for i in range(4)
        ]
        past_slot = Slot(
            id=uuid.uuid4(),
            service_date=YESTERDAY,
            starts_at=_at(12, 0, YESTERDAY),
            ends_at=_at(12, 15, YESTERDAY),
            capacity=30,
            booked=1,
        )
        with Session(engine, expire_on_commit=False) as session, session.begin():
            session.add_all([self.student, self.admin, self.thali, self.dosa])
            for day in (YESTERDAY, DAY):
                session.add(
                    ServiceDay(
                        service_date=day,
                        window_start=time(12, 0),
                        window_end=time(13, 0),
                        slot_len_min=15,
                        default_capacity=30,
                    )
                )
            session.flush()
            session.add_all([*self.slots, past_slot])
            session.flush()
            # Thali: 10 left, 4 allocated; yesterday 20 were sold, so HIGH risk today.
            session.add(
                DailyInventory(item_id=self.thali.id, service_date=DAY, total=14, allocated=4)
            )
            session.add(
                DailyInventory(item_id=self.dosa.id, service_date=DAY, total=50, allocated=1)
            )
            self._order(session, self.slots[0], self.thali, 4, OrderStatus.ACCEPTED)
            self._order(session, self.slots[1], self.dosa, 1, OrderStatus.ACCEPTED)
            self._order(session, past_slot, self.thali, 20, OrderStatus.PICKED_UP)

    def _order(
        self, session: Session, slot: Slot, item: MenuItem, qty: int, status: OrderStatus
    ) -> None:
        order = Order(id=uuid.uuid4(), student_id=self.student.id, slot_id=slot.id, status=status)
        session.add(order)
        session.flush()
        session.add(OrderLine(order_id=order.id, item_id=item.id, qty=qty))

    def auth(self, user: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


@pytest.fixture
def kitchen(engine: Engine, db_client: TestClient) -> Iterator[Kitchen]:
    # db_client truncates users, menu_items and service_days (and so the agent tables) after.
    yield Kitchen(engine)
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM rate_limits WHERE subject = :s"), {"s": DAILY_BUDGET_SUBJECT}
        )
        connection.execute(text("TRUNCATE agent_runs CASCADE"))


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def run_with(
    sessions: sessionmaker[Session],
) -> Iterator[Callable[..., tuple[uuid.UUID, AgentRunStatus, StubProvider]]]:
    """Queue an on-demand run and execute it with the scripted replies."""
    opened: list[Session] = []

    def run(
        *replies: object, now: datetime | None = None, provider: StubProvider | None = None
    ) -> tuple[uuid.UUID, AgentRunStatus, StubProvider]:
        stub = provider if provider is not None else StubProvider(replies)  # type: ignore[arg-type]
        session = sessions()
        opened.append(session)
        when = now or _at(11, 30)

        def llm(s: Session) -> GuardedLLMClient:
            return GuardedLLMClient(
                stub, s, daily_cap=50, breaker=CircuitBreaker(), cache=ResponseCache()
            )

        service = AgentService(session, llm)
        run_id = service.request_run(AgentTrigger.ON_DEMAND, None, when).id
        status = service.run_next(when)
        assert status is not None
        return run_id, status, stub

    yield run
    for session in opened:
        session.close()


def _run(engine: Engine, run_id: uuid.UUID) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT status, source, input_hash, report FROM agent_runs WHERE id = :id"),
            {"id": run_id},
        ).mappings()
        return dict(row.one())


def _logged(engine: Engine, table: str, run_id: uuid.UUID) -> list[dict[str, Any]]:
    order = "seq" if table == "agent_tool_calls" else "id"
    with engine.connect() as connection:
        rows = connection.execute(
            text(f"SELECT * FROM {table} WHERE run_id = :id ORDER BY {order}"), {"id": run_id}
        ).mappings()
        return [dict(r) for r in rows]


def _proposals(engine: Engine, run_id: uuid.UUID) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT * FROM proposals WHERE run_id = :id ORDER BY created_at"), {"id": run_id}
        ).mappings()
        return [dict(r) for r in rows]


# --- Acceptance criteria --------------------------------------------------------


def test_tc_us39_ac1_scheduled_run_starts_at_lead_time_with_a_report(
    kitchen: Kitchen, sessions: sessionmaker[Session], engine: Engine
) -> None:
    stub = StubProvider(
        [_tools(_call("get_inventory_levels")), reply("Thali is likely to run out.")]
    )

    def llm(s: Session) -> GuardedLLMClient:
        return GuardedLLMClient(
            stub, s, daily_cap=50, breaker=CircuitBreaker(), cache=ResponseCache()
        )

    with sessions() as session:
        service = AgentService(session, llm)
        # P-AGENT_LEAD is 30 minutes before the 12:00 window.
        assert service.enqueue_scheduled(_at(11, 29)) is None
        run = service.enqueue_scheduled(_at(11, 30))
        assert run is not None
        assert run.trigger is AgentTrigger.SCHEDULED
        assert service.run_next(_at(11, 30)) is AgentRunStatus.SUCCEEDED
        # Once a day: no second scheduled run.
        assert service.enqueue_scheduled(_at(11, 45)) is None

    saved = _run(engine, run.id)
    report = saved["report"]
    assert saved["status"] == "SUCCEEDED"
    assert saved["source"] == "LLM"
    assert report["service_date"] == DAY.isoformat()
    assert {row["item_name"] for row in report["demand_summary"]} == {"Paneer Thali", "Masala Dosa"}
    risks = {row["item_name"]: row["risk"] for row in report["forecast"]}
    assert risks == {"Paneer Thali": "high", "Masala Dosa": "low"}
    assert report["narrative"] == "Thali is likely to run out."


def test_tc_us39_ac2_a_second_run_while_one_is_in_progress_gets_409(
    kitchen: Kitchen, db_client: TestClient
) -> None:
    headers = kitchen.auth(kitchen.admin)
    first = db_client.post("/api/v1/admin/agent/runs", headers=headers)

    second = db_client.post("/api/v1/admin/agent/runs", headers=headers)

    assert first.status_code == 202
    assert first.json()["status"] == "QUEUED"
    assert second.status_code == 409
    assert second.json()["detail"]["running_run_id"] == first.json()["id"]


def test_tc_us39_ac3_every_call_is_logged_and_no_student_data_reaches_the_llm(
    kitchen: Kitchen, run_with: Callable[..., Any], engine: Engine
) -> None:
    run_id, status, stub = run_with(
        _tools(_call("get_pending_orders"), _call("get_menu_config")),
        _tools(_call("get_historical_demand"), _call("get_slot_utilisation")),
        _tools(_call("get_inventory_levels")),
        reply("done"),
    )

    assert status is AgentRunStatus.SUCCEEDED
    tool_calls = _logged(engine, "agent_tool_calls", run_id)
    assert [c["tool"] for c in tool_calls] == [
        "get_pending_orders",
        "get_menu_config",
        "get_historical_demand",
        "get_slot_utilisation",
        "get_inventory_levels",
    ]
    assert [c["seq"] for c in tool_calls] == [1, 2, 3, 4, 5]
    assert all(c["outcome"] == "OK" for c in tool_calls)
    llm_calls = _logged(engine, "agent_llm_calls", run_id)
    assert len(llm_calls) == 4
    assert all(c["model"] == "stub" and c["prompt_tokens"] == 10 for c in llm_calls)
    sent = json.dumps([repr(request) for request in stub.requests])
    for secret in (STUDENT_NAME, STUDENT_EMAIL, str(kitchen.student.id), "Zebediah"):
        assert secret not in sent


# --- Tools and proposals ----------------------------------------------------------


def test_an_unknown_tool_is_rejected_logged_and_audited(
    kitchen: Kitchen, run_with: Callable[..., Any], engine: Engine
) -> None:
    run_id, status, stub = run_with(_tools(_call("update_price", {"item": "x"})), reply("ok"))

    assert status is AgentRunStatus.SUCCEEDED
    [logged] = _logged(engine, "agent_tool_calls", run_id)
    assert (logged["tool"], logged["outcome"]) == ("update_price", "REJECTED")
    tool_reply = stub.requests[1].messages[-1]
    assert "unknown tool" in (tool_reply.content or "")
    with engine.connect() as connection:
        event = (
            connection.execute(
                text(
                    "SELECT actor_role, after FROM audit_log WHERE action = 'AGENT_TOOL_REJECTED' "
                    "AND actor_id = :run"
                ),
                {"run": str(run_id)},
            )
            .mappings()
            .one()
        )
    assert event["actor_role"] == "AGENT"
    assert event["after"]["tool"] == "update_price"


def test_proposals_are_stored_pending_with_their_expiry(
    kitchen: Kitchen, run_with: Callable[..., Any], engine: Engine
) -> None:
    thali, dosa = str(kitchen.thali.id), str(kitchen.dosa.id)
    second_slot = kitchen.slots[1]
    run_id, status, _ = run_with(
        _tools(
            _call(
                "propose_replenishment_plan",
                {
                    "lines": [{"item_id": thali, "additional_portions": 10}],
                    "rationale": "Thali sold 20 yesterday; 10 left.",
                },
            ),
            _call(
                "propose_prep_priority",
                {"slot_id": str(second_slot.id), "item_ids": [dosa], "rationale": "x"},
            ),
            _call(
                "propose_item_disable",
                {"item_id": dosa, "reason": "fryer down", "rationale": "Staff note."},
            ),
        ),
        reply("Three proposals drafted."),
    )

    assert status is AgentRunStatus.SUCCEEDED
    proposals = {p["type"]: p for p in _proposals(engine, run_id)}
    assert set(proposals) == {"REPLENISH", "PREP_PRIORITY", "DISABLE"}
    assert all(p["status"] == "PENDING" and p["source"] == "LLM" for p in proposals.values())
    assert all(p["target_date"] == DAY for p in proposals.values())
    # FR-56: prep priority expires at its slot's start, the others when the window opens.
    assert proposals["PREP_PRIORITY"]["target_slot_id"] == second_slot.id
    assert proposals["PREP_PRIORITY"]["expires_at"] == second_slot.starts_at
    assert proposals["REPLENISH"]["expires_at"] == _at(12, 0)
    assert proposals["DISABLE"]["expires_at"] == _at(12, 0)
    for kind, row in proposals.items():
        parse_payload(ProposalType(kind), row["payload"])
    assert _run(engine, run_id)["report"]["proposals"] == 3


def test_a_later_proposal_for_the_same_target_replaces_the_earlier(
    kitchen: Kitchen, run_with: Callable[..., Any], engine: Engine
) -> None:
    thali = str(kitchen.thali.id)

    def plan(portions: int) -> ToolCall:
        return _call(
            "propose_replenishment_plan",
            {"lines": [{"item_id": thali, "additional_portions": portions}], "rationale": "r"},
        )

    run_id, _, _ = run_with(_tools(plan(5)), _tools(plan(12)), reply("done"))

    [proposal] = _proposals(engine, run_id)
    assert proposal["payload"]["lines"][0]["additional_portions"] == 12


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (_call("propose_replenishment_plan", "{not json"), "not valid JSON"),
        (_call("propose_replenishment_plan", "[1, 2]"), "must be a JSON object"),
        (_call("propose_replenishment_plan", {"lines": [], "rationale": "r"}), "lines"),
        (
            _call("propose_item_disable", {"item_id": "nope", "reason": "r", "rationale": "r"}),
            "item_id",
        ),
        (
            _call(
                "propose_prep_priority",
                {"slot_id": str(uuid.uuid4()), "item_ids": [], "rationale": "r"},
            ),
            "not a slot of this service date",
        ),
        (_call("get_inventory_levels", {"service_date": "2020-01-01"}), "takes no arguments"),
    ],
    ids=["bad-json", "not-object", "empty-lines", "bad-uuid", "unknown-slot", "read-with-args"],
)
def test_malformed_tool_calls_are_logged_invalid_and_stage_nothing(
    kitchen: Kitchen,
    run_with: Callable[..., Any],
    engine: Engine,
    call: ToolCall,
    message: str,
) -> None:
    run_id, status, stub = run_with(_tools(call), reply("done"))

    assert status is AgentRunStatus.SUCCEEDED
    [logged] = _logged(engine, "agent_tool_calls", run_id)
    assert logged["outcome"] == "INVALID"
    assert message in logged["result_summary"]
    assert message in (stub.requests[1].messages[-1].content or "")
    assert _proposals(engine, run_id) == []


def test_during_service_only_prep_priority_can_be_proposed(
    kitchen: Kitchen, run_with: Callable[..., Any], engine: Engine
) -> None:
    thali, dosa = str(kitchen.thali.id), str(kitchen.dosa.id)
    run_id, _, _ = run_with(
        _tools(
            _call(
                "propose_replenishment_plan",
                {"lines": [{"item_id": thali, "additional_portions": 5}], "rationale": "r"},
            ),
            _call(
                "propose_prep_priority",
                {"slot_id": str(kitchen.slots[1].id), "item_ids": [dosa], "rationale": "r"},
            ),
        ),
        reply("done"),
        now=_at(12, 5),
    )

    logged = _logged(engine, "agent_tool_calls", run_id)
    assert [(c["tool"], c["outcome"]) for c in logged] == [
        ("propose_replenishment_plan", "INVALID"),
        ("propose_prep_priority", "OK"),
    ]
    assert "service window has opened" in logged[0]["result_summary"]
    [proposal] = _proposals(engine, run_id)
    assert proposal["target_slot_id"] == kitchen.slots[1].id


def test_a_slot_that_has_started_cannot_be_prioritised(
    kitchen: Kitchen, run_with: Callable[..., Any], engine: Engine
) -> None:
    run_id, _, _ = run_with(
        _tools(
            _call(
                "propose_prep_priority",
                {
                    "slot_id": str(kitchen.slots[0].id),
                    "item_ids": [str(kitchen.thali.id)],
                    "rationale": "r",
                },
            )
        ),
        reply("done"),
        now=_at(12, 5),
    )

    [logged] = _logged(engine, "agent_tool_calls", run_id)
    assert (logged["outcome"], logged["result_summary"]) == (
        "INVALID",
        "the slot has already started",
    )


# --- Failures and limits ----------------------------------------------------------


def test_without_a_key_the_heuristic_plans_and_says_why(
    kitchen: Kitchen, sessions: sessionmaker[Session], engine: Engine
) -> None:
    def no_llm(s: Session) -> GuardedLLMClient:
        return GuardedLLMClient(
            None, s, daily_cap=50, breaker=CircuitBreaker(), cache=ResponseCache()
        )

    with sessions() as session:
        service = AgentService(session, no_llm)
        run_id = service.request_run(AgentTrigger.ON_DEMAND, None, _at(11, 30)).id
        assert service.run_next(_at(11, 30)) is AgentRunStatus.SUCCEEDED

    saved = _run(engine, run_id)
    assert saved["source"] == "HEURISTIC"
    assert "no LLM API key" in saved["report"]["fallback_reason"]
    assert saved["report"]["forecast"]
    [llm_call] = _logged(engine, "agent_llm_calls", run_id)
    assert llm_call["outcome"] == "ERROR"


def test_a_run_that_exceeds_its_tool_calls_falls_back_to_the_heuristic(
    kitchen: Kitchen, sessions: sessionmaker[Session], engine: Engine
) -> None:
    looping = StubProvider([_tools(_call("get_menu_config")) for _ in range(10)])
    with sessions() as session:
        run_id = AgentService(session).request_run(AgentTrigger.ON_DEMAND, None, _at(11, 30)).id
        with session.begin():
            session.execute(
                text("UPDATE agent_runs SET status = 'RUNNING' WHERE id = :id"), {"id": run_id}
            )
        llm = GuardedLLMClient(
            looping, session, daily_cap=50, breaker=CircuitBreaker(), cache=ResponseCache()
        )
        orchestrator = PlanningOrchestrator(session, llm, RunLimits(max_calls=3, timeout_s=30))
        status = orchestrator.execute(run_id, DAY, _at(11, 30))

    assert status is AgentRunStatus.SUCCEEDED
    saved = _run(engine, run_id)
    assert saved["source"] == "HEURISTIC"
    assert "3 tool calls" in saved["report"]["fallback_reason"]
    assert len(_logged(engine, "agent_tool_calls", run_id)) == 3


def test_an_unexpected_error_marks_the_run_failed(
    kitchen: Kitchen, sessions: sessionmaker[Session], engine: Engine
) -> None:
    def broken(request: object) -> LLMResponse:
        raise RuntimeError("bug")

    def llm(s: Session) -> GuardedLLMClient:
        return GuardedLLMClient(
            StubProvider([broken]), s, daily_cap=50, breaker=CircuitBreaker(), cache=ResponseCache()
        )

    with sessions() as session:
        service = AgentService(session, llm)
        run_id = service.request_run(AgentTrigger.ON_DEMAND, None, _at(11, 30)).id
        with pytest.raises(RuntimeError, match="bug"):
            service.run_next(_at(11, 30))

    saved = _run(engine, run_id)
    assert saved["status"] == "FAILED"
    assert saved["report"] == {"error": "internal error"}


def test_an_abandoned_run_does_not_block_a_new_one(
    kitchen: Kitchen, sessions: sessionmaker[Session], engine: Engine
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO agent_runs (trigger, status, started_at) "
                "VALUES ('ON_DEMAND', 'RUNNING', :at)"
            ),
            {"at": _at(9, 0)},
        )

    with sessions() as session:
        run = AgentService(session).request_run(AgentTrigger.ON_DEMAND, None, _at(11, 30))

    assert run.status is AgentRunStatus.QUEUED
    with engine.connect() as connection:
        statuses = connection.execute(text("SELECT status FROM agent_runs")).scalars().all()
    assert sorted(statuses) == ["FAILED", "QUEUED"]


def test_no_scheduled_run_without_a_service_day(sessions: sessionmaker[Session]) -> None:
    with sessions() as session:
        assert AgentService(session).enqueue_scheduled(_at(11, 30, date(2030, 1, 1))) is None


def test_running_with_nothing_queued_does_nothing(
    kitchen: Kitchen, sessions: sessionmaker[Session]
) -> None:
    with sessions() as session:
        assert AgentService(session, lambda s: None).run_next(_at(11, 30)) is None  # type: ignore[arg-type,return-value]


def test_executing_needs_an_llm_factory(sessions: sessionmaker[Session]) -> None:
    with sessions() as session, pytest.raises(RuntimeError, match="LLM client factory"):
        AgentService(session).run_next(_at(11, 30))


# --- API ----------------------------------------------------------------------------


def test_run_history_and_detail(
    kitchen: Kitchen, run_with: Callable[..., Any], db_client: TestClient
) -> None:
    run_id, _, _ = run_with(_tools(_call("get_menu_config")), reply("briefing"))
    headers = kitchen.auth(kitchen.admin)

    history = db_client.get("/api/v1/admin/agent/runs", headers=headers)
    detail = db_client.get(f"/api/v1/admin/agent/runs/{run_id}", headers=headers)

    assert history.status_code == 200
    assert history.json()[0]["id"] == str(run_id)
    body = detail.json()
    assert body["status"] == "SUCCEEDED"
    assert body["report"]["narrative"] == "briefing"
    assert [c["tool"] for c in body["tool_calls"]] == ["get_menu_config"]
    assert body["proposals"] == []


def test_unknown_run_is_404(kitchen: Kitchen, db_client: TestClient) -> None:
    response = db_client.get(
        f"/api/v1/admin/agent/runs/{uuid.uuid4()}", headers=kitchen.auth(kitchen.admin)
    )
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("method", "path"), [("post", ""), ("get", ""), ("get", f"/{uuid.uuid4()}")]
)
def test_only_the_administrator_uses_the_agent_endpoints(
    kitchen: Kitchen, db_client: TestClient, method: str, path: str
) -> None:
    response = db_client.request(
        method, f"/api/v1/admin/agent/runs{path}", headers=kitchen.auth(kitchen.student)
    )
    assert response.status_code == 403


def test_the_worker_runs_the_agent_jobs() -> None:
    names = {job.name for job in all_jobs()}
    assert {"agent-schedule", "agent-runner"} <= names


def test_agent_jobs_use_the_app_session(
    configured_database: None, kitchen: Kitchen, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.agent import jobs

    monkeypatch.setattr(jobs.clock, "now", lambda: _at(11, 30))
    jobs.schedule_planning_run()
    with Session(kitchen.engine) as session:
        run = session.query(AgentRun).one()
    assert run.trigger is AgentTrigger.SCHEDULED

    monkeypatch.setattr(
        jobs,
        "get_llm_client",
        lambda s: GuardedLLMClient(
            StubProvider([reply("ok")]),
            s,
            daily_cap=50,
            breaker=CircuitBreaker(),
            cache=ResponseCache(),
        ),
    )
    jobs.execute_queued_run()
    with Session(kitchen.engine) as session:
        assert session.get(AgentRun, run.id).status is AgentRunStatus.SUCCEEDED  # type: ignore[union-attr]


# --- Forecast (pure) ------------------------------------------------------------------


def _snapshot(available: int, allocated: int, history: list[int], slots: int = 4) -> Snapshot:
    item = "item-1"
    return Snapshot(
        service_date=DAY.isoformat(),
        pending_orders=[],
        inventory_levels=[
            {
                "item_id": item,
                "total": available + allocated,
                "allocated": allocated,
                "available": available,
            }
        ],
        slot_utilisation=[
            {"slot_id": f"s{i}", "starts_at": _at(12, 15 * i).isoformat()} for i in range(slots)
        ],
        historical_demand=[
            {
                "service_date": (DAY - timedelta(days=d + 1)).isoformat(),
                "item_id": item,
                "portions": p,
            }
            for d, p in enumerate(history)
        ],
        menu_config=[{"item_id": item, "name": "Thali"}],
    )


@pytest.mark.parametrize(
    ("available", "allocated", "history", "risk", "stockout"),
    [
        (0, 10, [], Risk.HIGH, "s0"),  # sold out already
        (10, 0, [20], Risk.HIGH, "s1"),  # 20 expected over 4 slots: 10 by the second
        (10, 0, [8], Risk.MEDIUM, None),  # 8 >= 70 % of 10
        (10, 0, [4, 2], Risk.LOW, None),  # mean of 3
        (10, 5, [], Risk.LOW, None),  # no history: forecast = allocated, nothing more expected
    ],
)
def test_forecast_risk_and_stockout_slot(
    available: int, allocated: int, history: list[int], risk: Risk, stockout: str | None
) -> None:
    [row] = forecast(_snapshot(available, allocated, history), _at(11, 30))

    assert row["risk"] == risk.value
    assert row["stockout_slot_id"] == stockout


def test_forecast_after_the_last_slot_has_no_stockout_slot() -> None:
    [row] = forecast(_snapshot(5, 0, [50]), _at(14, 0))
    assert row["risk"] == Risk.HIGH.value
    assert row["stockout_slot_id"] is None


def test_removed_items_are_left_out_of_the_forecast() -> None:
    snapshot = _snapshot(5, 0, [1])
    gone = Snapshot(**{**snapshot.__dict__, "menu_config": []})
    assert build_report(gone, _at(11, 30))["forecast"] == []


# --- US-43: planning without the LLM (FR-59, FR-64, NFR-17) -------------------------


def _unreachable_openai() -> OpenAIProvider:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = openai.OpenAI(
        api_key="sk-test",
        base_url="https://llm.unreachable.test/v1",
        max_retries=0,
        timeout=1.0,
        http_client=httpx.Client(transport=httpx.MockTransport(refuse)),
    )
    return OpenAIProvider(client, "gpt-test")


def _guarded(provider: Any, session: Session, *, daily_cap: int = 50) -> GuardedLLMClient:
    return GuardedLLMClient(
        provider,
        session,
        daily_cap=daily_cap,
        breaker=CircuitBreaker(),
        cache=ResponseCache(),
        now=lambda: _at(11, 30),
    )


def test_tc_us43_ac1_unreachable_llm_gives_a_heuristic_report_within_5_s(
    kitchen: Kitchen, sessions: sessionmaker[Session], engine: Engine
) -> None:
    with sessions() as session:
        service = AgentService(session, lambda s: _guarded(_unreachable_openai(), s))
        run_id = service.request_run(AgentTrigger.ON_DEMAND, None, _at(11, 30)).id
        started = time_module.monotonic()
        status = service.run_next(_at(11, 30))
        elapsed = time_module.monotonic() - started

    assert status is AgentRunStatus.SUCCEEDED
    assert elapsed < 5
    saved = _run(engine, run_id)
    assert saved["source"] == "HEURISTIC"
    assert saved["report"]["narrative"].startswith("Heuristic briefing")
    risks = {row["item_name"]: row["risk"] for row in saved["report"]["forecast"]}
    assert risks["Paneer Thali"] == "high"
    proposals = {p["type"]: p for p in _proposals(engine, run_id)}
    # Thali: forecast 20 (yesterday), 4 allocated, 10 available -> 6 short.
    assert proposals["REPLENISH"]["payload"] == {
        "lines": [{"item_id": str(kitchen.thali.id), "additional_portions": 6}]
    }
    assert proposals["PREP_PRIORITY"]["target_slot_id"] == kitchen.slots[0].id
    assert {p["source"] for p in proposals.values()} == {"HEURISTIC"}


def test_tc_us43_ac1_a_slow_llm_does_not_slow_ordering(
    kitchen: Kitchen, sessions: sessionmaker[Session], db_client: TestClient
) -> None:
    release = threading.Event()

    def slow(request: object) -> LLMResponse:
        release.wait(timeout=10)
        return reply("late briefing")

    with sessions() as session:
        service = AgentService(session, lambda s: _guarded(StubProvider([slow]), s))
        service.request_run(AgentTrigger.ON_DEMAND, None, _at(11, 30))
        runner = threading.Thread(target=service.run_next, args=(_at(11, 30),))
        runner.start()
        try:
            started = time_module.monotonic()
            menu = db_client.get(
                f"/api/v1/menu?date={DAY.isoformat()}", headers=kitchen.auth(kitchen.student)
            )
            elapsed = time_module.monotonic() - started
        finally:
            release.set()
            runner.join(timeout=10)

    assert menu.status_code == 200
    assert elapsed < 1


def test_tc_us43_ac2_daily_cap_reached_uses_the_heuristic(
    kitchen: Kitchen, sessions: sessionmaker[Session], engine: Engine
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO rate_limits (subject, window_start, count) VALUES (:s, :w, 50)"),
            {"s": DAILY_BUDGET_SUBJECT, "w": datetime.combine(DAY, time.min, tzinfo=IST)},
        )
    stub = StubProvider([reply("never used")])

    with sessions() as session:
        service = AgentService(session, lambda s: _guarded(stub, s, daily_cap=50))
        run_id = service.request_run(AgentTrigger.ON_DEMAND, None, _at(11, 30)).id
        assert service.run_next(_at(11, 30)) is AgentRunStatus.SUCCEEDED

    saved = _run(engine, run_id)
    assert saved["source"] == "HEURISTIC"
    assert "daily LLM cap" in saved["report"]["fallback_reason"]
    assert stub.requests == []


def test_tc_us43_ac3_identical_tool_data_reuses_the_earlier_result(
    kitchen: Kitchen, run_with: Callable[..., Any], engine: Engine
) -> None:
    thali = str(kitchen.thali.id)
    stub = StubProvider(
        [
            _tools(
                _call(
                    "propose_replenishment_plan",
                    {"lines": [{"item_id": thali, "additional_portions": 6}], "rationale": "r"},
                )
            ),
            reply("first briefing"),
        ]
    )
    first_id, _, _ = run_with(provider=stub)
    requests_after_first = len(stub.requests)

    second_id, status, _ = run_with(provider=stub, now=_at(11, 40))

    assert status is AgentRunStatus.SUCCEEDED
    assert len(stub.requests) == requests_after_first  # no LLM request
    second = _run(engine, second_id)
    assert second["report"]["reused_from"] == str(first_id)
    assert second["report"]["narrative"] == "first briefing"
    assert second["source"] == "LLM"
    assert _proposals(engine, second_id) == []  # the first run's proposals stand
    assert len(_proposals(engine, first_id)) == 1


def test_changed_tool_data_is_planned_again(
    kitchen: Kitchen, run_with: Callable[..., Any], engine: Engine
) -> None:
    first_id, _, _ = run_with(reply("first"))
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE daily_inventory SET total = total + 5 WHERE item_id = :i"),
            {"i": kitchen.dosa.id},
        )

    second_id, _, stub = run_with(reply("second"))

    assert len(stub.requests) == 1
    assert "reused_from" not in _run(engine, second_id)["report"]
    assert _run(engine, second_id)["input_hash"] != _run(engine, first_id)["input_hash"]


# --- Heuristic rules (pure) -------------------------------------------------------------


def _heuristic_snapshot(available: int, history: int, pending: dict[str, int]) -> Snapshot:
    slots = [
        {"slot_id": str(SLOT_IDS[i]), "starts_at": _at(12, 15 * i).isoformat()} for i in range(4)
    ]
    return Snapshot(
        service_date=DAY.isoformat(),
        pending_orders=[
            {
                "slot_id": str(SLOT_IDS[1]),
                "starts_at": slots[1]["starts_at"],
                "item_id": item,
                "portions": n,
            }
            for item, n in pending.items()
        ],
        inventory_levels=[
            {"item_id": str(ITEM_A), "total": available, "allocated": 0, "available": available},
            {"item_id": str(ITEM_B), "total": 50, "allocated": 0, "available": 50},
        ],
        slot_utilisation=slots,
        historical_demand=[
            {"service_date": YESTERDAY.isoformat(), "item_id": str(ITEM_A), "portions": history}
        ],
        menu_config=[
            {"item_id": str(ITEM_A), "name": "A"},
            {"item_id": str(ITEM_B), "name": "B"},
        ],
    )


ITEM_A = uuid.UUID(int=0xA)
ITEM_B = uuid.UUID(int=0xB)
SLOT_IDS = [uuid.UUID(int=0x100 + i) for i in range(4)]


def _heuristic(snapshot: Snapshot, now: datetime, repl_max: int = 200) -> heuristic.HeuristicPlan:
    report = build_report(snapshot, now)
    return heuristic.plan(snapshot, report, ToolRegistry(snapshot, now, repl_max), repl_max)


def test_heuristic_replenishes_the_shortfall_and_orders_prep_by_pending_portions() -> None:
    snapshot = _heuristic_snapshot(10, 30, {str(ITEM_B): 2, str(ITEM_A): 7})

    plan = _heuristic(snapshot, _at(11, 30))

    by_type = {p.type: p for p in plan.proposals}
    assert by_type[ProposalType.REPLENISH].payload == {
        "lines": [{"item_id": str(ITEM_A), "additional_portions": 20}]
    }
    assert by_type[ProposalType.PREP_PRIORITY].payload == {"item_ids": [str(ITEM_A), str(ITEM_B)]}
    assert "High stock-out risk: A." in plan.narrative


def test_heuristic_proposes_disabling_when_the_shortfall_exceeds_p_repl_max() -> None:
    plan = _heuristic(_heuristic_snapshot(10, 300, {}), _at(11, 30), repl_max=200)

    [proposal] = plan.proposals
    assert proposal.type is ProposalType.DISABLE
    assert proposal.payload["item_id"] == str(ITEM_A)


def test_heuristic_during_service_only_prioritises_a_slot_not_yet_started() -> None:
    plan = _heuristic(_heuristic_snapshot(10, 30, {str(ITEM_A): 1}), _at(12, 5))

    [proposal] = plan.proposals
    assert proposal.type is ProposalType.PREP_PRIORITY
    # 12:05: the 12:00 slot has started, so the pending 12:15 slot is prioritised.
    assert proposal.target_slot_id == SLOT_IDS[1]


def test_heuristic_with_nothing_at_risk_drafts_nothing() -> None:
    plan = _heuristic(_heuristic_snapshot(50, 5, {}), _at(11, 30))

    assert plan.proposals == []
    assert "No item is at high risk." in plan.narrative


# --- US-42: bad agent output never reaches the Administrator (FR-58) -----------------


def test_tc_us42_ac1_a_hallucinated_item_is_discarded_with_the_reason_logged(
    kitchen: Kitchen, run_with: Callable[..., Any], engine: Engine
) -> None:
    ghost = str(uuid.uuid4())
    run_id, status, stub = run_with(
        _tools(
            _call(
                "propose_replenishment_plan",
                {"lines": [{"item_id": ghost, "additional_portions": 5}], "rationale": "r"},
            )
        ),
        reply("done"),
    )

    assert status is AgentRunStatus.SUCCEEDED
    [logged] = _logged(engine, "agent_tool_calls", run_id)
    assert logged["outcome"] == "DISCARDED"
    assert f"item {ghost} does not exist or is not ACTIVE" in logged["result_summary"]
    assert "proposal discarded" in (stub.requests[1].messages[-1].content or "")
    assert _proposals(engine, run_id) == []
    assert _run(engine, run_id)["source"] == "LLM"  # one bad output: the model got its retry


def test_tc_us42_ac2_invalid_json_twice_retries_once_then_uses_the_heuristic(
    kitchen: Kitchen, run_with: Callable[..., Any], engine: Engine
) -> None:
    bad = _call("propose_replenishment_plan", "{not json")
    run_id, status, stub = run_with(_tools(bad), _tools(bad), reply("never reached"))

    assert status is AgentRunStatus.SUCCEEDED
    assert len(stub.requests) == 2  # the original request and exactly one retry
    assert "not valid JSON" in (stub.requests[1].messages[-1].content or "")
    saved = _run(engine, run_id)
    assert saved["source"] == "HEURISTIC"
    assert "invalid output after 1 retry" in saved["report"]["fallback_reason"]
    assert [c["outcome"] for c in _logged(engine, "agent_tool_calls", run_id)] == [
        "INVALID",
        "INVALID",
    ]
    assert {p["source"] for p in _proposals(engine, run_id)} == {"HEURISTIC"}


def test_tc_us42_ac3_ten_thousand_portions_fails_the_bounds_check(
    kitchen: Kitchen, run_with: Callable[..., Any], engine: Engine
) -> None:
    run_id, _, _ = run_with(
        _tools(
            _call(
                "propose_replenishment_plan",
                {
                    "lines": [{"item_id": str(kitchen.thali.id), "additional_portions": 10_000}],
                    "rationale": "r",
                },
            )
        ),
        reply("done"),
    )

    [logged] = _logged(engine, "agent_tool_calls", run_id)
    assert logged["outcome"] == "DISCARDED"
    assert "10000 additional portions exceed P-REPL_MAX (200)" in logged["result_summary"]
    assert _proposals(engine, run_id) == []


def _validator_snapshot() -> Snapshot:
    return Snapshot(
        service_date=DAY.isoformat(),
        pending_orders=[
            {"slot_id": "slot-1", "starts_at": "x", "item_id": "a", "portions": 3},
        ],
        inventory_levels=[{"item_id": "a", "total": 450, "allocated": 0, "available": 450}],
        slot_utilisation=[],
        historical_demand=[],
        menu_config=[{"item_id": "a", "name": "A"}, {"item_id": "b", "name": "B"}],
    )


@pytest.mark.parametrize(
    ("proposal_type", "payload", "slot", "reason"),
    [
        (ProposalType.DISABLE, {"item_id": "gone"}, None, "does not exist or is not ACTIVE"),
        (ProposalType.PREP_PRIORITY, {"item_ids": ["a", "gone"]}, "slot-1", "not ACTIVE"),
        (ProposalType.PREP_PRIORITY, {"item_ids": ["b"]}, "slot-1", "no pending orders"),
        (
            ProposalType.REPLENISH,
            {"lines": [{"item_id": "b", "additional_portions": 5}]},
            None,
            "no inventory for the date",
        ),
        (
            ProposalType.REPLENISH,
            {"lines": [{"item_id": "a", "additional_portions": 201}]},
            None,
            "exceed P-REPL_MAX (200)",
        ),
        (
            ProposalType.REPLENISH,
            {"lines": [{"item_id": "a", "additional_portions": 51}]},
            None,
            "would exceed 500 portions",
        ),
    ],
)
def test_validator_rejects(
    proposal_type: ProposalType, payload: dict[str, object], slot: str | None, reason: str
) -> None:
    with pytest.raises(ProposalRejectedError, match=re.escape(reason)):
        OutputValidator(_validator_snapshot(), repl_max=200).check(proposal_type, payload, slot)


@pytest.mark.parametrize(
    ("proposal_type", "payload", "slot"),
    [
        (ProposalType.DISABLE, {"item_id": "b"}, None),
        (ProposalType.PREP_PRIORITY, {"item_ids": ["a"]}, "slot-1"),
        (ProposalType.REPLENISH, {"lines": [{"item_id": "a", "additional_portions": 50}]}, None),
    ],
)
def test_validator_accepts_sound_proposals(
    proposal_type: ProposalType, payload: dict[str, object], slot: str | None
) -> None:
    OutputValidator(_validator_snapshot(), repl_max=200).check(proposal_type, payload, slot)
