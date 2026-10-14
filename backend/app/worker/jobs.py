"""Periodic jobs and the registry the worker schedules them from.

A job is a plain function that opens its own session and transaction, so it can
also be called directly from a test. Jobs must be idempotent: a crash can make a
run repeat, and the worker gives no stronger guarantee than "at most one at a
time" (ADR-07).

To add a job, append a `Job` to `JOBS` from the module that owns the logic, e.g.
the hold sweeper (FR-34), auto-prep (FR-44), proposal expiry (FR-56) and the
scheduled agent run (FR-50).
"""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Job:
    name: str
    func: Callable[[], None]
    every_s: float
    # FR-34: the hold sweeper also runs once at start-up, before the first interval.
    run_at_startup: bool = False


JOBS: list[Job] = []


def all_jobs() -> list[Job]:
    """Every job the worker runs; modules are imported here so the worker owns the list."""
    from app.modules.agent.jobs import AGENT_JOBS
    from app.modules.proposals.jobs import PROPOSAL_JOBS

    return [*JOBS, *AGENT_JOBS, *PROPOSAL_JOBS]
