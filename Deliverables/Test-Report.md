# Test Report: Unit, Integration, System and Adversarial

Caf@IITK, Deliverable 3.

## 1. Run of record

| | |
|---|---|
| Commit | `d97912c` (tag `d3`, the Sprint 3 release on `main`) |
| Date | 6 Nov 2026, on a team member's laptop (Linux, Docker 29.8) |
| Backend | Python 3.12.3, pytest 9.2, pytest-cov 7.1, Hypothesis 6.170, testcontainers 4.15 with `postgres:16` |
| Client | Flutter 3.47.5 (stable), `flutter test --coverage` |
| Commands | `cd backend && pytest --cov` · `cd app && flutter test --coverage` (as in CI) |

The same suites run in CI on every PR and on every push to `develop` and `main`. All four required checks passed on the release PR, #109.

## 2. Results

| Suite | Tests | Passed | Failed | Skipped | Time |
|---|---|---|---|---|---|
| Backend (pytest) | 1,378 | 1,363 | 0 | 15 | 10 min 34 s |
| Client (flutter test) | 159 | 159 | 0 | 0 | 35 s |
| **Total** | **1,537** | **1,522** | **0** | **15** | |

The 15 skips are by design:
- **12 public routes** in the access-control matrix (`test_security_campaign.py`). They need no role, so there is nothing to deny.
- **2 US-31 peak tests** (`test_us31_peak.py`). They run only when pointed at a deployed stack (`CAF_PERF_BASE_URL`), which was not done (`Performance-Report.md` §4).
- **1 hostile idempotency key** that cannot be sent as an HTTP header at all.

Coverage: backend 98.3%, client 97.2% (`Coverage-Report.md`).

## 3. Test levels

Every backend test that touches the database runs against **real PostgreSQL 16** in a testcontainers container, migrated to the head revision. None uses SQLite or a mocked database. Each test file is classified by the most realistic thing it drives:

| Level | Definition used | Files | Tests | Passed | Skipped |
|---|---|---|---|---|---|
| Unit | Pure logic, no database or network: the order state machine, the pricing engine, the permission table, tokens, password hashing, request schemas, the mockpay app in-process | 11 | 216 | 216 | 0 |
| Integration | The API in-process (FastAPI `TestClient`) against real PostgreSQL; services and repositories against real PostgreSQL; the payment gateway against real mockpay over HTTP | 46 | 751 | 751 | 0 |
| System | Separate processes over real HTTP: **two `caf-api` processes and mockpay** (`live_stack`); the load generator; the database container stopped and restarted under a running API | 6 | 50 | 48 | 2 |
| Adversarial | Tests whose job is to break the system: the security campaign and fuzzing over every route, NUL and hostile input, strict-validation and error-leakage tests, fault injection at every SQL statement, prompt injection against the agent | 5 | 361 | 348 | 13 |
| Client (widget and flow) | Flutter widget tests driving whole screens and flows (Student, Kitchen, Administrator) against a scripted fake server; unit tests of the API layer, interceptors and error mapping | 6 | 159 | 159 | 0 |

### 3.1 Unit tests (216)

| File | Tests | What it covers |
|---|---|---|
| `test_order_state_machine.py` | 72 | Every allowed and forbidden order transition (FR-29, FR-16; SRS Table 4.6-A), as a pure function |
| `test_permissions.py` | 41 | The permission table matches SRS Table 4.1-A for every role |
| `test_pricing_properties.py` | 26 | Property-based (Hypothesis) and table-driven tests of the FR-24 pricing engine (CAFIITK-187): the engine matches an independent reference; only the highest covering rule applies; the subsidy never exceeds its amount or cap; the payable is never below zero; an extra rule or eligibility never raises the price; the result is deterministic and order-independent (NFR-38) |
| `test_pricing_engine.py` | 25 | Price, discount and subsidy arithmetic in integer paise |
| `test_mockpay.py` | 18 | The mock payment provider (FR-41): authorise, void, refund and the outcome control |
| `test_identity_schemas.py` | 11 | Registration and login request validation |
| `test_tokens.py` | 10 | JWT signing, expiry, forged and unsigned tokens, refresh-token hashing, production secret checks |
| `test_openapi_export.py`, `test_cors.py`, `test_health.py`, `test_security.py` | 13 | OpenAPI export, CORS policy, health endpoints, Argon2 hashing |

### 3.2 Integration tests (751)

These are the acceptance tests for most user stories. Each acceptance criterion has a test named after it, for example `test_tc_us28_ac5_two_concurrent_cancels_record_exactly_one_refund`. `Requirements-Traceability.md` maps every criterion to its test.

| Area | Files | Tests |
|---|---|---|
| Ordering: place, modify, cancel, track, history, portions, idempotency, retry, payment gateway and failure, hold sweeper, Administrator cancel | 12 | 166 |
| Catalogue, inventory and slots | 9 | 162 |
| Pricing: quotes, discount rules, subsidy | 3 | 96 |
| Agent: schema, runs, LLM client, spend report, proposal decisions | 5 | 132 |
| Identity, staff accounts, authorisation, login audit | 5 | 58 |
| Kitchen queue and transitions, auto-prep | 3 | 28 |
| Administrator monitoring, audit trail, observability, metrics, schema, seeding, database roles, worker, session | 9 | 109 |

### 3.3 System tests (50)

| File | Tests | What it covers |
|---|---|---|
| `test_order_rush.py` | 8 | US-30: 200 concurrent orders over two API processes, 10 runs; concurrent modify and cancel; 60-second mixed workload (`Concurrency-Test-Report.md`) |
| `test_rate_limits.py` | 11 | Login and order rate limits, including 20 parallel guesses across two API processes |
| `test_db_down.py` | 10 | US-32: the database stopped under load, then restarted (`Failure-Recovery-Test-Report.md`) |
| `test_loadgen.py`, `test_perf.py` | 19 | The load generator and the performance harness themselves |
| `test_us31_peak.py` | 2 (skipped) | US-31 latency targets against a deployed stack; not run (see §2) |

### 3.4 Adversarial tests (361)

| File | Tests | What it covers |
|---|---|---|
| `test_security_campaign.py` | 307 (13 skipped) | Access to all 46 routes for every caller type; token misuse; business-logic abuse; fuzzing of every body, query parameter, path parameter and idempotency key (`Security-Threat-Model.md` §3) |
| `test_request_safety.py` | 19 | Unknown fields and parameters refused (NFR-22); no internals in any error (NFR-23) |
| `test_agent_authority.py` | 17 | Unregistered tools, prompt injection through item descriptions, and the `caf_agent` role denied every write outside its grants (US-41) |
| `test_failure_injection.py` | 12 | A fault at every SQL statement of seven write operations; no network call inside a transaction (NFR-3, NFR-6) |
| `test_nul_text.py` | 6 | NUL characters in body and query text answer 422, not 500 |

### 3.5 Client tests (159)

| File | What it covers |
|---|---|
| `student_flow_test.dart` | Menu, slot picker, the full price breakdown, placing, tracking, cancelling and modifying an order, My orders |
| `staff_dashboards_test.dart` | Kitchen queue and transitions; Administrator items, service day, monitoring, staff, agent, proposals, discounts and subsidy |
| `auth_flow_test.dart` | Login, registration, role-based routing; the route guard |
| `interceptors_test.dart` | Token refresh on 401; retries with back-off reusing the idempotency key (NFR-18) |
| `errors_test.dart`, `api_test.dart` | Error messages shown to users; the API provider |

## 4. Manual system testing

- **D2 end-to-end walkthrough** on Docker Compose, in Chrome and Firefox (including a 360 px viewport): Administrator setup, a Student order, an agent run, and the kitchen working the order through to pickup. Recorded in the release PR #63.
- **Failure demonstrations on Docker Compose:** `caf-api` killed mid-payment (PR #68); the database stopped and started (PR #73).
- **Android:** the APK built from the Flutter codebase, run on a phone against the local stack through `adb reverse` (CAFIITK-192, PR #99).
- **Deployed stack:** HTTPS, CORS, health and reachability checks on AWS, plus a browser check as the Administrator (`Deployment-Documentation.md` §7).

## 5. Defects found by testing

Seven defects were raised as Jira Bugs in Sprint 3, all fixed with a regression test (details in `Project-Report.md` §2.5 and `Security-Threat-Model.md` §4):

| Found by | Bugs |
|---|---|
| Adversarial testing | CAFIITK-200, 203, 204 |
| Security testing | CAFIITK-199 |
| Unit/integration testing | CAFIITK-201 |
| Code review | CAFIITK-202, 205 |

## 6. Known gaps

- **No browser-automation end-to-end tests.** The client is tested with widget tests against a fake server; end-to-end runs were manual.
- **US-31 not run against a deployed stack.** Its two tests are skipped, and the latency targets NFR-8, 9 and 12 are not met locally.
- **No tests on AWS** beyond the deployment checks in §4.
