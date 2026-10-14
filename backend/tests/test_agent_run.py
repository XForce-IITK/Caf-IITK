"""US-39: the planning agent run (FR-50 - FR-52, FR-62), against real PostgreSQL.

The LLM is the scripted StubProvider behind the real GuardedLLMClient, so every
guard runs; only the provider is fake. Data reads, logs and proposals go through
the caf_agent role exactly as in production.
"""

import json
import uuid
from collections.abc import Callable, Iterator
from datetime import date, datetime, time, timedelta
from typing import Any

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
from app.modules.agent.forecast import Risk, Snapshot, build_report, forecast
from app.modules.agent.llm import (
    DAILY_BUDGET_SUBJECT,
    CircuitBreaker,
    GuardedLLMClient,
    LLMResponse,
    ResponseCache,
    ToolCall,
)
from app.modules.agent.orchestrator import PlanningOrchestrator, RunLimits
from app.modules.agent.service import AgentService
from app.modules.agent.stub import StubProvider, reply
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
                {"slot_id": str(second_slot.id), "item_ids": [dosa, thali], "rationale": "x"},
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
    thali = str(kitchen.thali.id)
    run_id, _, _ = run_with(
        _tools(
            _call(
                "propose_replenishment_plan",
                {"lines": [{"item_id": thali, "additional_portions": 5}], "rationale": "r"},
            ),
            _call(
                "propose_prep_priority",
                {"slot_id": str(kitchen.slots[0].id), "item_ids": [thali], "rationale": "r"},
            ),
            _call(
                "propose_prep_priority",
                {"slot_id": str(kitchen.slots[3].id), "item_ids": [thali], "rationale": "r"},
            ),
        ),
        reply("done"),
        now=_at(12, 20),
    )

    outcomes = [(c["tool"], c["outcome"]) for c in _logged(engine, "agent_tool_calls", run_id)]
    assert outcomes == [
        ("propose_replenishment_plan", "INVALID"),
        ("propose_prep_priority", "INVALID"),  # its slot already started
        ("propose_prep_priority", "OK"),
    ]
    [proposal] = _proposals(engine, run_id)
    assert proposal["target_slot_id"] == kitchen.slots[3].id


# --- Failures and limits ----------------------------------------------------------


def test_without_an_llm_the_run_fails_with_the_reason_and_still_has_the_numbers(
    kitchen: Kitchen, sessions: sessionmaker[Session], engine: Engine
) -> None:
    def no_llm(s: Session) -> GuardedLLMClient:
        return GuardedLLMClient(
            None, s, daily_cap=50, breaker=CircuitBreaker(), cache=ResponseCache()
        )

    with sessions() as session:
        service = AgentService(session, no_llm)
        run_id = service.request_run(AgentTrigger.ON_DEMAND, None, _at(11, 30)).id
        assert service.run_next(_at(11, 30)) is AgentRunStatus.FAILED

    saved = _run(engine, run_id)
    assert "no LLM API key" in saved["report"]["error"]
    assert saved["report"]["forecast"]
    assert saved["input_hash"]
    [llm_call] = _logged(engine, "agent_llm_calls", run_id)
    assert llm_call["outcome"] == "ERROR"


def test_a_run_that_exceeds_its_tool_calls_fails(
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

    assert status is AgentRunStatus.FAILED
    assert "3 tool calls" in _run(engine, run_id)["report"]["error"]
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
