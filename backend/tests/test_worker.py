"""caf-worker: exactly one leader runs the jobs (SADD ADR-07), against real PostgreSQL.

Each Worker holds its advisory lock on its own connection, i.e. its own database
session, which is what separate worker processes would do.
"""

import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from app.worker.jobs import Job
from app.worker.leader import WORKER_LOCK_KEY, LeaderLock
from app.worker.main import LostLeadershipError, Worker

BACKEND_DIR = Path(__file__).resolve().parent.parent
FAST = {"retry_s": 0.05, "heartbeat_s": 0.05}


class Runs:
    """Records which worker ran a job, thread-safely."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.by: list[str] = []

    def job(self, label: str, every_s: float = 0.05, **kwargs: bool) -> Job:
        def run() -> None:
            with self._lock:
                self.by.append(label)

        return Job(name=f"record-{label}", func=run, every_s=every_s, **kwargs)


def _wait_for(condition: Callable[[], bool], timeout_s: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.02)


@pytest.fixture
def background() -> Iterator[Callable[[Worker], threading.Event]]:
    """Runs workers in threads and stops them all after the test."""
    started: list[tuple[threading.Thread, threading.Event]] = []

    def start(worker: Worker) -> threading.Event:
        stop = threading.Event()
        thread = threading.Thread(target=worker.run, args=(stop,), daemon=True)
        thread.start()
        started.append((thread, stop))
        return stop

    yield start
    for thread, stop in started:
        stop.set()
        thread.join(timeout=5)


def test_only_one_worker_runs_the_jobs(
    engine: Engine, background: Callable[[Worker], threading.Event]
) -> None:
    runs = Runs()
    first = Worker(engine, [runs.job("first")], **FAST)
    second = Worker(engine, [runs.job("second")], **FAST)

    background(first)
    _wait_for(lambda: first.is_leader)
    background(second)
    _wait_for(lambda: runs.by.count("first") >= 5)

    assert not second.is_leader
    assert "second" not in runs.by


def test_a_follower_takes_over_when_the_leader_stops(
    engine: Engine, background: Callable[[Worker], threading.Event]
) -> None:
    runs = Runs()
    first = Worker(engine, [runs.job("first")], **FAST)
    second = Worker(engine, [runs.job("second")], **FAST)
    stop_first = background(first)
    _wait_for(lambda: first.is_leader)
    background(second)

    stop_first.set()

    _wait_for(lambda: second.is_leader)
    _wait_for(lambda: "second" in runs.by)


def test_a_second_worker_cannot_start_while_one_leads(engine: Engine) -> None:
    first = Worker(engine, [])
    first.start()
    try:
        with pytest.raises(RuntimeError, match="leader lock"):
            Worker(engine, []).start()
    finally:
        first.stop()


def test_start_up_jobs_run_before_the_first_interval(engine: Engine) -> None:
    runs = Runs()
    worker = Worker(engine, [runs.job("sweeper", every_s=3600, run_at_startup=True)])

    worker.start()
    try:
        assert runs.by == ["sweeper"]
    finally:
        worker.stop()


def test_a_failing_job_keeps_being_scheduled(
    engine: Engine, background: Callable[[Worker], threading.Event]
) -> None:
    attempts: list[int] = []

    def flaky() -> None:
        attempts.append(1)
        raise RuntimeError("boom")

    worker = Worker(engine, [Job(name="flaky", func=flaky, every_s=0.05)], **FAST)
    background(worker)

    _wait_for(lambda: len(attempts) >= 3)
    assert worker.is_leader


def test_losing_the_lock_connection_stops_the_leader(engine: Engine) -> None:
    runs = Runs()
    worker = Worker(engine, [runs.job("leader")], **FAST)
    stop = threading.Event()
    errors: list[BaseException] = []

    def run() -> None:
        try:
            worker.run(stop)
        except LostLeadershipError as error:
            errors.append(error)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    _wait_for(lambda: worker.is_leader)

    # Simulate the database dropping the leader's session.
    with engine.begin() as connection:
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_locks "
                "WHERE locktype = 'advisory' AND objid = :key AND granted"
            ),
            {"key": WORKER_LOCK_KEY},
        )
    thread.join(timeout=5)

    assert errors
    assert not worker.is_leader
    # The lock went with the session, so another worker can lead now.
    other = LeaderLock(engine)
    assert other.try_acquire()
    other.release()


def test_worker_process_starts_and_stops_on_sigterm(database_url: str) -> None:
    env = os.environ | {"CAF_DATABASE_URL": database_url}
    process = subprocess.Popen(
        [sys.executable, "-m", "app.worker"],
        cwd=BACKEND_DIR,
        env=env,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        lock = LeaderLock(create_probe_engine(database_url))
        _wait_for(lambda: not _try_and_release(lock), timeout_s=30)
        process.send_signal(signal.SIGTERM)
        _, stderr = process.communicate(timeout=30)
    finally:
        if process.poll() is None:
            process.kill()

    assert process.returncode == 0
    assert "leader: scheduled" in stderr


def create_probe_engine(database_url: str) -> Engine:
    from sqlalchemy import create_engine

    return create_engine(database_url)


def _try_and_release(lock: LeaderLock) -> bool:
    """True if the lock was free (so no worker leads yet); never keeps it."""
    acquired = lock.try_acquire()
    lock.release()
    return acquired
