"""The performance harness itself (tests/perf.py), at a small scale.

The measurements of record (NFR-8 - NFR-12) run against the Compose stack or AWS and
are reported in Deliverables/Performance-Report.md; these tests prove the harness
drives every workload and counts what it sees correctly.
"""

from collections.abc import Iterator

import perf
import pytest
from conftest import LiveStack
from sqlalchemy import Engine, text


@pytest.fixture
def perf_db(engine: Engine) -> Iterator[Engine]:
    yield engine
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE users, menu_items, service_days, discount_rules CASCADE"))
        connection.execute(text("TRUNCATE agent_runs CASCADE"))


@pytest.mark.parametrize(
    ("p", "expected"),
    [(50, 20.0), (95, 40.0), (99, 40.0), (100, 40.0), (1, 10.0)],
)
def test_percentiles_are_nearest_rank(p: float, expected: float) -> None:
    latencies = perf.Latencies()
    for ms in (40.0, 10.0, 30.0, 20.0):
        latencies.add(ms, 201)
    assert latencies.percentile(p) == expected


def test_server_view_is_the_difference_between_two_scrapes() -> None:
    family = "caf_http_request_duration_seconds"
    route = frozenset({("method", "POST"), ("route", "/api/v1/orders"), ("status", "201")})

    def scraped(count: float, total: float, buckets: dict[str, float]) -> perf.Samples:
        samples = {(f"{family}_count", route): count, (f"{family}_sum", route): total}
        for le, n in buckets.items():
            samples[(f"{family}_bucket", route | {("le", le)})] = n
        return samples

    before = scraped(5, 1.0, {"0.1": 5, "0.5": 5, "+Inf": 5})
    after = scraped(105, 21.0, {"0.1": 50, "0.5": 101, "+Inf": 105})
    assert perf.server_view(before, after) == {
        "POST /api/v1/orders": {"count": 100, "mean_ms": 200.0, "p95": "≤ 500 ms"}
    }


def test_designed_rejections_are_not_errors() -> None:
    latencies = perf.Latencies()
    for status in (201, 409, 422, 500, 503, 599):
        latencies.add(1.0, status)
    assert latencies.errors == 3


def test_every_workload_runs_at_a_small_scale(live_stack: LiveStack, perf_db: Engine) -> None:
    runs = perf.run(
        perf.WORKLOADS,
        live_stack.api_urls[0],
        live_stack.mockpay_url,
        perf_db,
        scale=0.05,
        fresh=True,
    )
    results = [r for run in runs for r in run.results]
    measured = [r for r in results if r.met is not None]
    # NFR-8, NFR-10, the heuristic run, the NFR-12 orders, and four reads for each of
    # NFR-9 and NFR-12.
    assert len(measured) == 12
    for result in measured:
        assert result.figures.get("errors", 0) == 0, result
        if "requests" in result.figures:
            assert result.figures["requests"] > 0, result

    def first(prefix: str) -> perf.Result:
        return next(r for r in results if r.workload.startswith(prefix))

    assert first("NFR-8:").figures["statuses"] == {201: 10}
    assert first("NFR-10:").figures["statuses"] == {201: 60}
    assert first("NFR-11:").figures["status"] == "SUCCEEDED"
    assert "| NFR-8" in perf.markdown(runs)

    # The server counted the same order requests the client sent, and their lock waits.
    nfr8_server = next(run for run in runs if run.workload == "nfr8").server
    assert nfr8_server["POST /api/v1/orders"]["count"] == 10
    assert "lock wait: daily_inventory" in nfr8_server
