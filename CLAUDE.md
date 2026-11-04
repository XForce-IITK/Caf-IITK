# Caf@IITK

Campus cafeteria pre-order and pickup-slot platform. CS455 Software Engineering course project (IIT Kanpur, 2026), Team XForce. Repo: `XForce-IITK/Caf-IITK`. Jira project key: `CAFIITK` (site `cafiitk.atlassian.net`). The Deliverable 1 documents say `CAF`; the real key is `CAFIITK`.

## Current state

Sprints 1 and 2 are merged and released (D2). Sprint 3 ends with Deliverable 3 on 6 Nov 2026 and is closing out.
- **Work still open:**
  - the AWS deployment (CAFIITK-190), after which come the performance rerun of record and cost tracking (191);
  - the Android build (192);
  - the security campaign (185) and its bugs;
  - the final regression, traceability matrix and release (193, 197).
- **Commands:** see `README.md`.
- **`Deliverables/`** holds the proposal, SRS (v2.0), SADD, project management report, AI Engineering Log, `Requirements-Traceability.md` and `Performance-Report.md`.
- **Source of truth:** the SRS and SADD for behaviour and design; read the relevant section before implementing anything.

Backend (`backend/`):
- **Layout:**
  - module packages under `app/modules/`: `identity`, `catalogue`, `inventory`, `slots`, `pricing`, `ordering`, `payments`, `audit`, `kitchen`, `proposals`, `agent`;
  - Alembic migrations from `0001` (all core tables from SADD Figure 2.5) onwards;
  - `mockpay` as a separate service;
  - `caf-worker` (`app/worker/`, leader-locked; modules register their jobs there).
- **Worker jobs:** the hold sweeper, the payment outbox (voids and refunds), auto-prep, agent runs and schedule, proposal expiry, rate-limit clean-up.
- **Student and Kitchen endpoints:**
  - register, login, refresh, logout, `me`;
  - browse the menu and slots, price quote;
  - place, track, cancel and modify an order (with idempotency keys);
  - the kitchen queue and its transitions.
- **Administrator endpoints:**
  - items: onboard, edit, remove, flag unavailable;
  - daily inventory, service days and slot capacity;
  - cancel any order;
  - order list and utilisation;
  - audit search;
  - discount rules, subsidy settings and eligibility;
  - staff accounts;
  - agent runs and proposal decisions.
- **Ops endpoints, outside `/api/v1`:** `/health`, `/ready`, `/metrics`.
- **Cross-cutting behaviour:**
  - a lost database connection is a 503 with `Retry-After` (`app/core/errors.py`);
  - JSON logs carry a correlation ID;
  - every application transaction runs as the `caf_app` role (migration 0005);
  - the connection pool is fixed with no overflow (`CAF_DB_POOL_SIZE`), and `WEB_CONCURRENCY` sets the gunicorn workers.
- **Performance harness:** `tests/perf.py`; see `Performance-Report.md` for how to run it.

Client (`app/`):
- the API client in `lib/api/generated/` is generated from `app/openapi.json`;
- login, register and role-based routing in `lib/auth/` and `lib/router.dart`;
- Dio interceptors in `lib/api/interceptors.dart`;
- the Student flow in `lib/student/`;
- the Kitchen dashboard in `lib/kitchen/`;
- the Administrator dashboard in `lib/admin/`: items, service day, monitoring, staff, agent and proposals.

Backend choices made in the skeleton: synchronous SQLAlchemy with psycopg 3 (FastAPI runs sync endpoints in a threadpool); deploy-time settings come from `CAF_*` environment variables (`app/core/config.py`); administrator-configurable parameters (SRS Table 4.0-B) are seeded into the `settings` table.

The `.docx` files are binary. To read one, extract the text from `word/document.xml` (pandoc is not installed on this machine).

## Deadlines

| Deliverable | Due |
|---|---|
| D2: implementation, agentic AI, sprint execution | 15 Oct 2026 |
| D3: testing, security, performance, deployment | 6 Nov 2026 |
| Scenario-based demo | 8–13 Nov 2026 |

## Planned stack and layout

- `/backend`: Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2, Alembic, PostgreSQL 16
- `/app`: Flutter Web (Dart), Riverpod, GoRouter, Dio, API client generated from the OpenAPI schema
- `/docs`, `/Deliverables` (the course brief requires deliverables in a folder with this name)
- Three processes from one backend codebase: `caf-api`, `caf-worker` (single leader via PostgreSQL advisory lock), and `mockpay` (separate mock payment service)
- Docker Compose locally; AWS EC2 + RDS free tier in deployment; GitHub Actions CI

## Workflow rules (from the course brief and SRS NFR-44/45)

- Branches: `CAFIITK-<issue>-<slug>`, off `develop`; `main` is protected.
- Every commit message and PR title starts with the Jira key, e.g. `CAFIITK-42: lock inventory and slot rows before decrement`.
- Significant changes merge through a PR with a description, test evidence and the Jira link, reviewed by someone other than the author.
- Each member commits from their own GitHub account. Never create artificial commits, backdated Jira issues or fabricated test results; the brief gives these no credit.
- Maintain `Deliverables/AI-Engineering-Log.md` as work proceeds (see below).
- After changing an endpoint or a request/response schema, run `app/tool/generate_api.sh` and commit the result in the same PR; CI fails if the generated client is stale (NFR-39). Never edit `app/lib/api/generated/` by hand. Endpoint function names become client method names, so keep them unique.

## AI Engineering Log

Claude keeps track of major AI-assisted work during a session and proposes log entries for `Deliverables/AI-Engineering-Log.md`, but asks before writing anything to the file.

- Log only major AI-assisted work: a feature, a design decision, a significant bug, a document or review. Skip routine questions, small edits and retries.
- Describe each entry at a high level: what was asked for, what the AI produced, how the team evaluated it, what was changed, and whether it was accepted, modified or rejected and why.
- Never paste exact prompts or raw transcripts, and do not list every prompt.
- Do not include dates or the name of the AI tool or model in entries.
- Record AI errors, hallucinations and risks in the summary table (`E<n>`, continuing the existing numbering).
- Only record a team evaluation or decision the team actually made; leave it as pending otherwise.

## Design invariants

- Layering: router → service → domain logic → repository → PostgreSQL. Services own transactions; only repositories issue SQL.
- No network call (mockpay, LLM) while a database transaction is open (NFR-6).
- Lock order with `SELECT … FOR UPDATE`: proposals → orders → `daily_inventory` (ascending item id) → `slots` (ascending slot id).
- Counters `allocated` and `booked` are guarded by CHECK constraints; never bypass them.
- Order flow is reserve → authorise → confirm, with timed holds released by the sweeper.
- Money is integer paise. The pricing engine and order state machine are pure functions.
- The agent connects as `caf_agent`: SELECT on the five `agent_*` views, INSERT on proposals and agent logs, no UPDATE or DELETE anywhere. Proposals take effect only through `ProposalService` under an Administrator's identity.
- `caf_app` has no UPDATE or DELETE on `audit_log`; audit rows are written in the same transaction as the change.
- Concurrency and transaction tests run against real PostgreSQL (testcontainers), never SQLite or mocks. Coverage gate is 80% for backend and client; generated client code is not counted.
- Client: every API call goes through `apiProvider`; create, modify and cancel carry one `newIdempotencyKey()` per user action, reused on a repeat of that action (NFR-18). The route guard is for usability only; the server enforces every permission.
