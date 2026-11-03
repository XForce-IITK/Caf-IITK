"""US-31 (CAFIITK-156; NFR-8, NFR-9, NFR-12) acceptance tests TC-US31-AC1..AC2.

These check the latency targets themselves, at full scale, against a running stack
(Docker Compose or AWS), using the CAFIITK-188 harness in perf.py. They need a stack
sized like the deployment, so they run only when pointed at one, and are skipped
otherwise; test_perf.py runs the same workloads at 5 % scale in CI to keep the
harness working. Results of record are in Deliverables/Performance-Report.md.

    cd backend
    CAF_JWT_SECRET=<the stack's secret> \\
    CAF_PERF_BASE_URL=http://localhost:8000 CAF_PERF_MOCKPAY_URL=http://localhost:8001 \\
    CAF_PERF_DATABASE_URL=postgresql+psycopg://caf:caf@localhost:5432/caf \\
        .venv/bin/pytest tests/test_us31_peak.py -s

Like perf.py, they leave their rows behind: point them at a development database only.
"""

import os
from collections.abc import Iterator

import perf
import pytest
from sqlalchemy import Engine, create_engine

BASE_URL = os.environ.get("CAF_PERF_BASE_URL")
MOCKPAY_URL = os.environ.get("CAF_PERF_MOCKPAY_URL", "http://localhost:8001")
DATABASE_URL = os.environ.get("CAF_PERF_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not (BASE_URL and DATABASE_URL),
    reason="set CAF_PERF_BASE_URL and CAF_PERF_DATABASE_URL to measure a running stack",
)


@pytest.fixture(scope="module")
def stack_db() -> Iterator[Engine]:
    assert DATABASE_URL is not None
    engine = create_engine(DATABASE_URL)
    yield engine
    engine.dispose()


def _measure(workload: str, engine: Engine) -> list[perf.Result]:
    assert BASE_URL is not None
    [run] = perf.run([workload], BASE_URL, MOCKPAY_URL, engine)
    print("\n" + perf.markdown([run]))
    return run.results


def _misses(results: list[perf.Result]) -> list[str]:
    return [
        f"{r.workload}: p95 {r.figures['p95_ms']} ms, p99 {r.figures['p99_ms']} ms "
        f"(target {r.target})"
        for r in results
        if not r.met
    ]


def test_tc_us31_ac1_order_creation_p95_and_p99_with_50_clients(stack_db: Engine) -> None:
    """50 concurrent clients create orders for one item and slot (NFR-8); the same burst
    under the NFR-12 design day, with 100 readers alongside, must hold the target too."""
    results = _measure("nfr8", stack_db)
    results += [r for r in _measure("nfr12", stack_db) if r.workload.endswith(": orders")]

    assert not _misses(results), _misses(results)


def test_tc_us31_ac2_reads_p95_with_100_users(stack_db: Engine) -> None:
    """100 concurrent users read the menu, slots, order history and kitchen queue (NFR-9)."""
    results = _measure("nfr9", stack_db)

    assert {r.workload.rsplit(": ", 1)[1] for r in results} == set(perf.READS)
    assert not _misses(results), _misses(results)
