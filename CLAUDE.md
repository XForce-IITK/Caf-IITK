# Caf@IITK

Campus cafeteria pre-order and pickup-slot platform. CS455 Software Engineering course project (IIT Kanpur, 2026), Team XForce. Repo: `XForce-IITK/Caf-IITK`. Jira project key: `CAFIITK` (site `cafiitk.atlassian.net`). The Deliverable 1 documents say `CAF`; the real key is `CAFIITK`.

## Current state

Repo skeleton in place (CAFIITK-169): `backend/` (FastAPI app, module packages under `app/modules/`, all core tables from SADD Figure 2.5 in Alembic migration `0001`, testcontainers test setup), `app/` (Flutter Web shell) and `docker-compose.yml`. No feature endpoints yet. See `README.md` for commands. `Documentation/` holds the proposal, SRS (v2.0), SADD, project management report and AI Engineering Log. The SRS and SADD are the source of truth for behaviour and design; read the relevant section before implementing anything.

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
- Maintain `Documentation/AI-Engineering-Log.md` as work proceeds (see below).

## AI Engineering Log

Claude keeps track of major AI-assisted work during a session and proposes log entries for `Documentation/AI-Engineering-Log.md`, but asks before writing anything to the file.

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
- Concurrency and transaction tests run against real PostgreSQL (testcontainers), never SQLite or mocks. Coverage gate is 80% for backend and client.
