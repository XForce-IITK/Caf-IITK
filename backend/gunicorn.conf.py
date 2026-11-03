"""gunicorn settings for caf-api (Dockerfile CMD).

Each worker process keeps its own metrics, so they write them to a shared directory
that GET /metrics adds up (prometheus_client multiprocess mode, app/core/metrics.py).
The variable must be set before any worker imports prometheus_client.
"""

import os
import shutil
from typing import Any

METRICS_DIR = os.environ.setdefault("PROMETHEUS_MULTIPROC_DIR", "/tmp/caf-metrics")

bind = "0.0.0.0:8000"
# Each process runs Python on one core at a time, so the host's CPUs decide this
# (CAFIITK-189). Each process also opens CAF_DB_POOL_SIZE connections.
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
worker_class = "uvicorn.workers.UvicornWorker"


def on_starting(server: Any) -> None:
    # Samples left by a previous run would be counted again.
    shutil.rmtree(METRICS_DIR, ignore_errors=True)
    os.makedirs(METRICS_DIR)


def child_exit(server: Any, worker: Any) -> None:
    from prometheus_client import multiprocess

    multiprocess.mark_process_dead(worker.pid)  # type: ignore[no-untyped-call]
