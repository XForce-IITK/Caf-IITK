# Code Coverage Report

Caf@IITK, Deliverable 3. Measured on the release commit `d97912c` (tag `d3`) on 6 Nov 2026, in the same run as `Test-Report.md` §2.

## 1. Summary

| Code | Measure | Covered | Total | Coverage | Gate |
|---|---|---|---|---|---|
| Backend (`backend/app`) | Lines | 5,370 | 5,439 | 98.7% | |
| | Branches | 759 | 796 | 95.4% | |
| | **Combined (coverage.py total)** | | | **98.3%** | 80% ✔ |
| Client (`app/lib`, generated API client excluded) | **Lines** | 2,359 | 2,428 | **97.2%** | 80% ✔ |

Both gates are enforced in CI on every PR: `pytest --cov` fails below 80% (`fail_under = 80` in `backend/pyproject.toml`), and the client job fails below 80% of lines. As the project rules require, the generated Dart client in `app/lib/api/generated/` is not counted. Including it, client line coverage is 82.0% (3,373 of 4,112 lines).

**Tools:** coverage.py 7.17 with branch coverage (`branch = true`, source `app`), through pytest-cov 7.1; Flutter 3.47.5 `flutter test --coverage` (LCOV).

## 2. Backend by package

| Package | Lines covered | Lines | Line % | Branches covered | Branches |
|---|---|---|---|---|---|
| `modules/catalogue` | 245 | 245 | 100.0% | 30 | 30 |
| `modules/inventory` | 95 | 95 | 100.0% | 8 | 8 |
| `modules/slots` | 222 | 222 | 100.0% | 28 | 28 |
| `modules/pricing` | 485 | 485 | 100.0% | 75 | 76 |
| `modules/payments` | 106 | 106 | 100.0% | 14 | 14 |
| `modules/audit` | 87 | 87 | 100.0% | 18 | 18 |
| `mockpay` | 139 | 139 | 100.0% | 22 | 22 |
| `models` | 343 | 343 | 100.0% | 0 | 0 |
| `api`, `db`, `main.py`, `openapi_export.py` | 122 | 122 | 100.0% | 4 | 4 |
| `modules/identity` | 427 | 430 | 99.3% | 46 | 46 |
| `modules/agent` | 925 | 934 | 99.0% | 170 | 178 |
| `modules/kitchen` | 165 | 167 | 98.8% | 12 | 12 |
| `modules/proposals` | 295 | 300 | 98.3% | 45 | 52 |
| `modules/ordering` | 1,169 | 1,192 | 98.1% | 184 | 194 |
| `core` | 403 | 412 | 97.8% | 68 | 74 |
| `seed.py` | 22 | 23 | 95.7% | 9 | 10 |
| `worker` | 120 | 137 | 87.6% | 26 | 30 |

## 3. What is not covered, and why

The 69 uncovered lines are concentrated in a few files:

| File | Coverage | Uncovered | Why |
|---|---|---|---|
| `worker/__main__.py`, `worker/main.py` (`main()`) | 0%, 85.7% | Process entry point: signal handlers, `sys.exit` | `test_worker_process_starts_and_stops_on_sigterm` runs this code as a separate process, and coverage is not collected from subprocesses. The leader logic it calls (`Worker.run`) is covered |
| `modules/ordering/outbox.py` | 85.3% | Logging-only branches: a refund larger than what was charged, a void with no authorisation, a payment delivered by another request at the same moment | Defensive branches for states the rest of the system should never produce; nothing in the suite constructs them |
| `modules/ordering/sweeper.py` | 88.4% | Early returns when the payment result or a release arrives in the instant between selecting and locking a hold | Race windows of a few milliseconds; the locking that makes them safe is tested, but these exact interleavings are not forced |
| `modules/ordering/jobs.py`, `modules/identity/jobs.py` | 86.4%, 75.0% | Three-line job wrappers that open a session from the global session maker and call the outbox deliverer or the rate-limit clean-up | The tests call `OutboxDeliverer` and `RateLimiter` directly with the test session, not through these wrappers |
| `core/metrics.py` | 93.1% | Non-HTTP ASGI events (lifespan) passed straight through; the multi-process registry used when `PROMETHEUS_MULTIPROC_DIR` is set | The test client sends only HTTP requests, and the tests run without that variable. `gunicorn.conf.py` sets it when the API runs under gunicorn |

None of the uncovered lines is in the order, pricing, inventory, slot or payment decision logic: those packages are at 98–100%.

## 4. Client by directory

| Directory | Lines covered | Lines | Coverage |
|---|---|---|---|
| `lib/admin` | 1,186 | 1,230 | 96.4% |
| `lib/student` | 759 | 776 | 97.8% |
| `lib/auth` | 134 | 137 | 97.8% |
| `lib/kitchen` | 132 | 135 | 97.8% |
| `lib/api` (hand-written: provider, interceptors, errors) | 83 | 83 | 100.0% |
| `lib/router.dart` | 32 | 32 | 100.0% |
| `lib/dashboards` | 28 | 28 | 100.0% |
| `lib/main.dart` | 5 | 7 | 71.4% |

`main.dart`'s two uncovered lines are `runApp` start-up, which widget tests do not run.

## 5. Reproducing

```sh
cd backend && .venv/bin/pytest --cov --cov-report=term-missing --cov-report=html   # htmlcov/index.html
cd app && flutter test --coverage                                                   # coverage/lcov.info
```

To get the client percentage the way CI counts it, run the awk script in the "Coverage gate (80%)" step of `.github/workflows/ci.yml` over `coverage/lcov.info`. It leaves out `lib/api/generated/`.

## 6. Limits of coverage as evidence

High line coverage shows that code ran under test, not that it is correct. The stronger evidence is in the other reports:
- the concurrency tests (`Concurrency-Test-Report.md`);
- fault injection at every SQL statement (`Failure-Recovery-Test-Report.md`);
- the security campaign over all 46 routes (`Security-Threat-Model.md`);
- the property-based pricing tests (`Test-Report.md` §3.1).
