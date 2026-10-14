"""The agent's caf-worker jobs: queue the scheduled run, and execute queued runs."""

from app.core import clock as clock
from app.db.session import get_sessionmaker
from app.modules.agent.client import get_llm_client
from app.modules.agent.service import AgentService
from app.worker.jobs import Job

# How often the worker checks whether the scheduled run is due, and for queued runs.
SCHEDULE_CHECK_S = 60
RUNNER_POLL_S = 5


def schedule_planning_run() -> None:
    with get_sessionmaker()() as session:
        AgentService(session).enqueue_scheduled(clock.now())


def execute_queued_run() -> None:
    with get_sessionmaker()() as session:
        AgentService(session, get_llm_client).run_next(clock.now())


AGENT_JOBS = [
    Job("agent-schedule", schedule_planning_run, SCHEDULE_CHECK_S),
    Job("agent-runner", execute_queued_run, RUNNER_POLL_S),
]
