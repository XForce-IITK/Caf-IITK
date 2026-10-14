"""Agent runs: queue on demand or on schedule, and execute in caf-worker (FR-50, ADR-01).

The API only queues a run; the worker executes it, so a slow LLM never holds an
API worker (NFR-17). At most one run is QUEUED or RUNNING at a time.
"""

import uuid
from collections.abc import Callable
from datetime import datetime, time, timedelta

from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.models.agent import AgentRun
from app.models.enums import AgentRunStatus, AgentTrigger
from app.modules.agent.llm import GuardedLLMClient
from app.modules.agent.orchestrator import PlanningOrchestrator, RunLimits
from app.modules.agent.repository import RunInProgressError, RunRepository

# A run still QUEUED or RUNNING after this many run timeouts was abandoned by a crash.
STALE_AFTER_TIMEOUTS = 3


class AgentService:
    def __init__(
        self,
        session: Session,
        llm_factory: Callable[[Session], GuardedLLMClient] | None = None,
    ) -> None:
        self.session = session
        self.runs = RunRepository(session)
        self._llm_factory = llm_factory

    def _limits(self) -> RunLimits:
        settings = get_settings()
        return RunLimits(settings.agent_max_calls, settings.agent_run_timeout_s)

    def request_run(
        self, trigger: AgentTrigger, requested_by: uuid.UUID | None, now: datetime
    ) -> AgentRun:
        """Queue a run; RunInProgressError carries the active run's ID (FR-50, US-39 AC2)."""
        stale_before = now - timedelta(seconds=STALE_AFTER_TIMEOUTS * self._limits().timeout_s)
        with self.session.begin():
            self.runs.fail_stale(stale_before)
            return self.runs.create(trigger, requested_by, now)

    def enqueue_scheduled(self, now: datetime) -> AgentRun | None:
        """Queue today's scheduled run once the time reaches window start - P-AGENT_LEAD."""
        today = now.date()
        with self.session.begin():
            day = self.runs.service_day(today)
            if day is None:
                return None
            lead = timedelta(minutes=int(self.runs.get_setting("P-AGENT_LEAD_MIN")))
            window_start = datetime.combine(today, day.window_start, tzinfo=clock.IST)
            window_end = datetime.combine(today, day.window_end, tzinfo=clock.IST)
            if not window_start - lead <= now < window_end:
                return None
            midnight = datetime.combine(today, time.min, tzinfo=clock.IST)
            if self.runs.scheduled_run_exists(since=midnight):
                return None
        try:
            return self.request_run(AgentTrigger.SCHEDULED, None, now)
        except RunInProgressError:
            return None  # an on-demand run is already planning today's service

    def run_next(self, now: datetime) -> AgentRunStatus | None:
        """Execute the oldest QUEUED run, if any."""
        if self._llm_factory is None:
            raise RuntimeError("AgentService needs an LLM client factory to execute runs")
        with self.session.begin():
            run = self.runs.claim_queued()
            if run is None:
                return None
            run_id = run.id
        orchestrator = PlanningOrchestrator(
            self.session, self._llm_factory(self.session), self._limits()
        )
        try:
            return orchestrator.execute(run_id, now.date(), now)
        except Exception:
            # Never leave a run RUNNING: it would block every later run until it goes stale.
            self.session.rollback()
            with self.session.begin():
                self.runs.finish(
                    run_id,
                    AgentRunStatus.FAILED,
                    source=None,
                    input_hash=None,
                    report={"error": "internal error"},
                )
            raise
