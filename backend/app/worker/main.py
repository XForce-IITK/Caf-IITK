"""caf-worker entry point: `python -m app.worker`.

Every worker instance waits for the leader lock; only the leader runs jobs. If
the leader loses its lock connection it stops its jobs and exits with a non-zero
status, so Docker restarts it as a follower.
"""

import logging
import signal
import sys
import threading
from collections.abc import Sequence
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import Engine

from app.worker.jobs import JOBS, Job, all_jobs
from app.worker.leader import LeaderLock

log = logging.getLogger("caf.worker")


class LostLeadershipError(RuntimeError):
    pass


def _guarded(job: Job) -> Any:
    def run() -> None:
        try:
            job.func()
        except Exception:
            # One failing run must not stop the job or the worker; the next interval retries.
            log.exception("job %s failed", job.name)

    return run


class Worker:
    def __init__(
        self,
        engine: Engine,
        jobs: Sequence[Job] = JOBS,
        *,
        retry_s: float = 5.0,
        heartbeat_s: float = 5.0,
    ) -> None:
        self.lock = LeaderLock(engine)
        self._jobs = tuple(jobs)
        self._retry_s = retry_s
        self._heartbeat_s = heartbeat_s
        self._scheduler: BackgroundScheduler | None = None

    @property
    def is_leader(self) -> bool:
        return self._scheduler is not None

    def start(self) -> None:
        """Become leader, run the start-up jobs, then schedule every job."""
        if not self.lock.try_acquire():
            raise RuntimeError("another worker holds the leader lock")
        for job in self._jobs:
            if job.run_at_startup:
                _guarded(job)()
        scheduler = BackgroundScheduler(timezone="UTC")
        for job in self._jobs:
            scheduler.add_job(
                _guarded(job),
                "interval",
                seconds=job.every_s,
                id=job.name,
                max_instances=1,
                coalesce=True,
            )
        scheduler.start()
        self._scheduler = scheduler
        log.info("leader: scheduled %d job(s)", len(self._jobs))

    def stop(self) -> None:
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=True)
            self._scheduler = None
        self.lock.release()

    def run(self, stop: threading.Event) -> None:
        """Wait to become leader, then run jobs until `stop` is set or leadership is lost."""
        try:
            while not stop.is_set():
                if self.lock.try_acquire():
                    self.start()
                    break
                stop.wait(self._retry_s)
            while not stop.is_set():
                if not self.lock.is_alive():
                    raise LostLeadershipError("lost the leader lock connection")
                stop.wait(self._heartbeat_s)
        finally:
            self.stop()


def main() -> int:
    from app.db.session import get_engine

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    try:
        Worker(get_engine(), all_jobs()).run(stop)
    except LostLeadershipError:
        log.exception("stopping")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
