"""SQL for agent runs.

`RunRepository` is run bookkeeping on the caf_app connection (SADD Figure 2.6
note): creating runs, claiming them, storing the report. `AgentDataRepository`
is everything done *as the agent*: each method runs in its own short
transaction under `SET LOCAL ROLE caf_agent`, so PostgreSQL enforces NFR-25.
The agent inserts without RETURNING, which would need SELECT it does not have.
"""

import json
import uuid
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.agent import AgentRun, Proposal
from app.models.capacity import ServiceDay
from app.models.enums import AgentRunStatus, AgentSource, AgentTrigger
from app.models.platform import Setting

ACTIVE = (AgentRunStatus.QUEUED, AgentRunStatus.RUNNING)
# How far back the historical-demand tool looks.
HISTORY_DAYS = 28


class RunInProgressError(Exception):
    def __init__(self, run_id: uuid.UUID) -> None:
        super().__init__(f"agent run {run_id} is in progress")
        self.run_id = run_id


def _json_ready(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, uuid.UUID):
            out[key] = str(value)
        elif isinstance(value, datetime | date | time):
            out[key] = value.isoformat()
        else:
            out[key] = value
    return out


class RunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_setting(self, key: str) -> Any:
        return self.session.scalar(select(Setting.value).where(Setting.key == key))

    def service_day(self, service_date: date) -> ServiceDay | None:
        return self.session.get(ServiceDay, service_date)

    def fail_stale(self, older_than: datetime) -> None:
        """A run left QUEUED or RUNNING by a crashed worker would block every new run."""
        self.session.execute(
            update(AgentRun)
            .where(AgentRun.status.in_(ACTIVE), AgentRun.started_at < older_than)
            .values(
                status=AgentRunStatus.FAILED,
                finished_at=datetime.now().astimezone(),
                report={"error": "abandoned: did not finish in time"},
            )
        )

    def active_run_id(self) -> uuid.UUID | None:
        return self.session.scalar(select(AgentRun.id).where(AgentRun.status.in_(ACTIVE)))

    def create(
        self, trigger: AgentTrigger, requested_by: uuid.UUID | None, now: datetime
    ) -> AgentRun:
        """Queue a run; the partial unique index allows only one active run (FR-50).

        started_at comes from the application clock, the same clock the schedule
        and the stale-run check compare it with.
        """
        run = AgentRun(
            trigger=trigger,
            requested_by=requested_by,
            status=AgentRunStatus.QUEUED,
            started_at=now,
        )
        try:
            with self.session.begin_nested():
                self.session.add(run)
        except IntegrityError as exc:
            if "uq_agent_runs_one_active" not in str(exc.orig):
                raise
            running = self.active_run_id()
            assert running is not None
            raise RunInProgressError(running) from exc
        return run

    def scheduled_run_exists(self, since: datetime) -> bool:
        return (
            self.session.scalar(
                select(AgentRun.id)
                .where(AgentRun.trigger == AgentTrigger.SCHEDULED, AgentRun.started_at >= since)
                .limit(1)
            )
            is not None
        )

    def claim_queued(self) -> AgentRun | None:
        run = self.session.scalar(
            select(AgentRun)
            .where(AgentRun.status == AgentRunStatus.QUEUED)
            .order_by(AgentRun.started_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if run is not None:
            run.status = AgentRunStatus.RUNNING
        return run

    def finish(
        self,
        run_id: uuid.UUID,
        status: AgentRunStatus,
        *,
        source: AgentSource | None,
        input_hash: str | None,
        report: dict[str, Any],
    ) -> None:
        self.session.execute(
            update(AgentRun)
            .where(AgentRun.id == run_id)
            .values(
                status=status,
                source=source,
                input_hash=input_hash,
                report=report,
                finished_at=datetime.now().astimezone(),
            )
        )

    def get(self, run_id: uuid.UUID) -> AgentRun | None:
        return self.session.get(AgentRun, run_id)

    def recent(self, limit: int) -> list[AgentRun]:
        return list(
            self.session.scalars(select(AgentRun).order_by(AgentRun.started_at.desc()).limit(limit))
        )

    def proposals_of(self, run_id: uuid.UUID) -> list[Proposal]:
        return list(
            self.session.scalars(
                select(Proposal).where(Proposal.run_id == run_id).order_by(Proposal.created_at)
            )
        )

    def tool_calls_of(self, run_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = self.session.execute(
            text(
                "SELECT seq, tool, args, result_summary, latency_ms, outcome "
                "FROM agent_tool_calls WHERE run_id = :run ORDER BY seq"
            ),
            {"run": run_id},
        ).mappings()
        return [dict(row) for row in rows]


class AgentDataRepository:
    """The agent's own database access, as caf_agent."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def _as_agent(self) -> None:
        self.session.execute(text("SET LOCAL ROLE caf_agent"))

    def _rows(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        with self.session.begin():
            self._as_agent()
            rows = self.session.execute(text(sql), params).mappings()
            return [_json_ready(dict(row)) for row in rows]

    def pending_orders(self, service_date: date) -> list[dict[str, Any]]:
        return self._rows(
            "SELECT slot_id, starts_at, item_id, portions, orders FROM agent_pending_demand "
            "WHERE service_date = :d ORDER BY starts_at, item_id",
            {"d": service_date},
        )

    def inventory_levels(self, service_date: date) -> list[dict[str, Any]]:
        return self._rows(
            "SELECT item_id, total, allocated, available FROM agent_inventory_levels "
            "WHERE service_date = :d ORDER BY item_id",
            {"d": service_date},
        )

    def slot_utilisation(self, service_date: date) -> list[dict[str, Any]]:
        return self._rows(
            "SELECT slot_id, starts_at, ends_at, capacity, booked, remaining "
            "FROM agent_slot_utilisation WHERE service_date = :d ORDER BY starts_at",
            {"d": service_date},
        )

    def historical_demand(self, service_date: date) -> list[dict[str, Any]]:
        return self._rows(
            "SELECT service_date, item_id, portions, orders FROM agent_historical_demand "
            "WHERE service_date < :d AND service_date >= :since ORDER BY service_date, item_id",
            {"d": service_date, "since": service_date - timedelta(days=HISTORY_DAYS)},
        )

    def menu_config(self) -> list[dict[str, Any]]:
        return self._rows(
            "SELECT item_id, name, description, category, price_paise, unavailable "
            "FROM agent_menu_config ORDER BY name",
            {},
        )

    def log_tool_call(
        self,
        run_id: uuid.UUID,
        seq: int,
        tool: str,
        args: dict[str, Any],
        result_summary: str,
        latency_ms: int,
        outcome: str,
    ) -> None:
        with self.session.begin():
            self._as_agent()
            self.session.execute(
                text(
                    "INSERT INTO agent_tool_calls "
                    "(run_id, seq, tool, args, result_summary, latency_ms, outcome) "
                    "VALUES (:run, :seq, :tool, CAST(:args AS jsonb), :summary, :latency, :outcome)"
                ),
                {
                    "run": run_id,
                    "seq": seq,
                    "tool": tool[:64],
                    "args": json.dumps(args),
                    "summary": result_summary,
                    "latency": latency_ms,
                    "outcome": outcome,
                },
            )

    def log_llm_call(
        self,
        run_id: uuid.UUID,
        model: str,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        latency_ms: int,
        outcome: str,
    ) -> None:
        with self.session.begin():
            self._as_agent()
            self.session.execute(
                text(
                    "INSERT INTO agent_llm_calls "
                    "(run_id, model, prompt_tokens, completion_tokens, latency_ms, outcome) "
                    "VALUES (:run, :model, :prompt, :completion, :latency, :outcome)"
                ),
                {
                    "run": run_id,
                    "model": model[:100],
                    "prompt": prompt_tokens,
                    "completion": completion_tokens,
                    "latency": latency_ms,
                    "outcome": outcome,
                },
            )

    def insert_proposals(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        with self.session.begin():
            self._as_agent()
            for row in rows:
                self.session.execute(
                    text(
                        "INSERT INTO proposals (id, run_id, type, target_date, target_slot_id, "
                        "payload, rationale, source, expires_at) VALUES (:id, :run_id, "
                        "CAST(:type AS proposal_type), :target_date, :target_slot_id, "
                        "CAST(:payload AS jsonb), :rationale, CAST(:source AS agent_source), "
                        ":expires_at)"
                    ),
                    row | {"payload": json.dumps(row["payload"])},
                )
