# Final Project Report and Jira Dashboard

Caf@IITK, a campus cafeteria pre-order and pickup-slot platform. CS455 Software Engineering, IIT Kanpur, 2026. Team XForce:

| Member | Roll no. | GitHub |
|---|---|---|
| Krishna Kumayu | 230576 | KrishnaKumayu |
| Kshitij Gupta | 230581 | Kshitijg18 |
| Rudransh Verma | 230881 | RudranshVerma23 |
| Shashi Bhidodiya | 230956 | iamshashi-10 |
| Suryansh Verma | 231061 | sury666 |

- **Repository:** `XForce-IITK/Caf-IITK`. **Jira:** project `CAFIITK` on `cafiitk.atlassian.net`.
- **Release:** tag `d3` (`main` at `d97912c`), deployed at https://dh3nmzc5y7ht8.cloudfront.net.
- **Data:** every figure in this report was read from Jira and GitHub on 6 Nov 2026, after Sprint 3 closed.

## 1. Outcome

| | Result |
|---|---|
| Functional requirements | 64 of 64 pass, including all 10 critical (★) requirements (`Requirements-Traceability.md`) |
| Non-functional requirements | 41 pass, 1 met on the local stack only (NFR-10), 3 not met (NFR-8, 9, 12: latency) |
| Jira | 199 issues, all Done; 3 sprints, all closed |
| Code | 109 merged PRs. 108 were approved by a member other than the author. The 109th (#97) was stacked on #96's branch, and its changes were reviewed when #96 merged |
| Tests | Backend and client suites pass on the release, above the 80% coverage gate (`Test-Report.md`, `Coverage-Report.md`) |
| Deployment | AWS EC2 + RDS behind CloudFront, within the free tier (`Deployment-Documentation.md`, `Cost-Report.md`) |
| Clients | Flutter web; Android APK from the same codebase |

## 2. Jira dashboard

The tables below are the dashboard's content, computed from Jira with JQL. A screenshot of the live Jira dashboard goes in `Deliverables/images/jira-dashboard.png`.

### 2.1 Issues by type and status

| Type | Count | Done |
|---|---|---|
| Epic | 12 | 12 |
| Story (user stories US-01 … US-43) | 43 | 43 |
| Task | 137 | 137 |
| Bug | 7 | 7 |
| **Total** | **199** | **199** |

Of the 137 tasks, 109 are requirement tasks (one per FR and NFR in SRS v2.0, unassigned by design). They are closed with evidence linked from the traceability matrix. The other 28 are engineering tasks: CI, observability, deployment, test campaigns and releases.

### 2.2 Issues by epic

| Epic | Child issues |
|---|---|
| Ordering (CAFIITK-10) | 41 |
| DevOps (CAFIITK-16) | 28 |
| Agent (CAFIITK-13) | 25 |
| Identity (CAFIITK-5) | 16 |
| Testing (CAFIITK-15) | 16 |
| Pricing (CAFIITK-9) | 12 |
| Catalogue (CAFIITK-6) | 11 |
| Audit (CAFIITK-12) | 10 |
| Slots (CAFIITK-8) | 8 |
| Client (CAFIITK-14) | 8 |
| Inventory (CAFIITK-7) | 6 |
| Kitchen (CAFIITK-11) | 6 |

### 2.3 Sprints

| Sprint | Dates | Issues | Stories | Tasks | Bugs | Completed |
|---|---|---|---|---|---|---|
| Sprint 1 | 27 Sep – 5 Oct | 18 | 14 | 4 | 0 | 5 Oct |
| Sprint 2 | 6 – 15 Oct | 24 | 15 | 9 | 0 | 15 Oct |
| Sprint 3 | 16 Oct – 6 Nov | 38 | 16 | 15 | 7 | 6 Nov |

The requirement tasks were not put in sprints. They were closed as the stories that satisfy them were done. Two Sprint 1 stories (CAFIITK-138, 155) carried over into Sprint 2. Sprint goals and the Gantt chart are in `Timeline.md`.

### 2.4 Assigned work by member

Story, task and bug assignments in Jira, and merged PRs by author on GitHub:

| Member | Stories | Tasks | Bugs | Merged PRs |
|---|---|---|---|---|
| Krishna Kumayu | 3 | 0 | 0 | 4 |
| Kshitij Gupta | 9 | 8 | 0 | 20 |
| Rudransh Verma | 9 | 4 | 0 | 21 |
| Shashi Bhidodiya | 14 | 4 | 1 | 21 |
| Suryansh Verma | 8 | 12 | 6 | 43 |

Areas each member led, from their PRs:

| Member | Areas |
|---|---|
| Krishna Kumayu | Student registration, login and token refresh, daily inventory (Sprint 1) |
| Kshitij Gupta | Repository skeleton; pricing engine, discount rules and subsidy; idempotency keys; the planning agent (schema, `caf_agent` role, LLM client, run loop, validation, heuristic fallback); caf-worker; auto-prep; health checks, metrics and JSON logging; strict validation; property-based pricing tests |
| Rudransh Verma | Order placement (reserve, authorise, confirm); modify, cancel and Administrator cancel; kitchen transitions; hold sweeper and payment outbox; the multi-process test stack and load generator; concurrency tests (US-30); database-loss handling; fault injection; performance measurement and optimisation |
| Shashi Bhidodiya | Permission matrix; item onboarding, editing, removal and the unavailable flag; service window, slots and capacity; the kitchen queue; proposal decisions and agent-authority tests; Kitchen and Administrator dashboards; order monitoring; audit log and search; US-31 tests; the AWS deployment and cost tracking |
| Suryansh Verma | CI and repository rules; mockpay and the payment gateway; menu and slot browsing; the generated API client, login and routing; the whole Student flow; order tracking and history; rate limits; staff accounts; the security campaign and its fixes; the Android build; Administrator discount and subsidy tabs; traceability and releases |

### 2.5 Defects

| Bug | Found by | Summary | Assignee | Open → resolved |
|---|---|---|---|---|
| CAFIITK-199 | Security testing | 422 responses echoed the rejected password | Suryansh | 3 Nov → 3 Nov |
| CAFIITK-200 | Adversarial testing | NUL in request text gave a 500 | Suryansh | 3 Nov → 3 Nov |
| CAFIITK-201 | Unit/integration testing | Tests signed tokens with the 17-byte default key | Suryansh | 3 Nov → 3 Nov |
| CAFIITK-202 | Code review | The Student menu did not show item categories (US-10 AC1) | Shashi | 3 Nov → 3 Nov |
| CAFIITK-203 | Adversarial testing | NUL in a query parameter gave a 500 | Suryansh | 5 Nov → 5 Nov |
| CAFIITK-204 | Adversarial testing | Audit `before_id` beyond bigint gave a 500 | Suryansh | 5 Nov → 5 Nov |
| CAFIITK-205 | Code review | Failed logins were not audited (FR-47) | Suryansh | 5 Nov → 5 Nov |

All 7 are fixed, with a regression test each. Bugs were raised in Jira only in Sprint 3, when the test campaigns ran. Earlier defects were fixed within the PR of the story that had them.

## 3. Process

- **Scrum in three sprints**, matching the deliverables: Sprint 1 the core order path, Sprint 2 the full feature set (D2), Sprint 3 hardening, testing and deployment (D3). Each sprint had a goal in Jira and ended with a release PR into `main`.
- **Requirements to code:** SRS v2.0 defines FR-1 … FR-64 and NFR-1 … NFR-45, each with a Jira requirement task. User stories US-01 … US-43 carry the acceptance criteria. Each test is named for the criterion it checks (`test_tc_us30_ac1_…`), so the traceability matrix can be checked by script.
- **Definition of Done** (D1 report §3.6): reviewed and approved by another member; CI green (lint, type-check, the full suite, the 80% coverage gates, the web build, the secret scan); tests added or updated, with a regression test for every bug fixed.
- **AI-assisted engineering:** recorded in `AI-Engineering-Log.md`, including the AI's errors (E-numbers) and how the team evaluated each output.

## 4. Configuration management

| Practice | How |
|---|---|
| Branches | `CAFIITK-<issue>-<slug>` off `develop`; `main` changes only by release PR |
| Commits and PRs | Every commit message and PR title starts with a Jira key; CI enforces it (NFR-44, PR #100) |
| Review | A repository ruleset requires one approval from someone other than the author, four green checks, and an up-to-date branch |
| Releases | Merge commits (not squash) keep every member's commits attributed on `main`; tags `d2`, `d3` |
| Generated code | The Dart API client is generated from the OpenAPI schema; CI fails if it is stale (NFR-39) |
| Database | Alembic migrations 0001–0007, linear history, the same chain locally and on RDS |
| Secrets | Environment variables only; gitleaks scans the full history on every run |

## 5. What went well and what did not

**Went well**
- **Correctness under concurrency was proven, not assumed.** The 200-order rush, the modify-versus-cancel races and fault injection at every SQL statement all run against real PostgreSQL, across two API processes (`Concurrency-Test-Report.md`, `Failure-Recovery-Test-Report.md`).
- **Security testing covered every route.** The access-control matrix fails CI if a route is added without an entry. Security, adversarial and code-review testing found five security-relevant defects, and all were fixed before release (`Security-Threat-Model.md` §4).
- **Every requirement is traceable** to a Jira task, a test and a PR.

**Did not go well**
- **Latency targets (NFR-8, 9, 12) were not met** on the local stack. CAFIITK-189 removed the lock contention but not the CPU limit. The AWS load run that would have given the numbers of record was not done before the deadline (`Performance-Report.md` §4).
- **Work was closed in bursts at sprint ends.** About three quarters of all issues (143 of 187) were resolved on four days: 5 Oct, 15 Oct, 3 Nov and 4 Nov (`Timeline.md` §4). Mid-sprint progress was hard to see on the board.
- **The deployment came late.** It went live on 5 Nov, one day before D3, which left no time for a load run or a soak period on AWS. It also exposed one defect that local testing could not: the RDS role grant fixed by migration 0007.
- **Uneven Jira assignment.** Krishna's work is concentrated in Sprint 1.
- **No real LLM on the deployment.** A real LLM run was recorded locally for D2; the deployed agent uses the heuristic planner.

## 6. Deliverable 3 documents

| Brief item | Document |
|---|---|
| Unit, integration, system and adversarial test reports | `Test-Report.md` |
| Code coverage report | `Coverage-Report.md` |
| Concurrency test report | `Concurrency-Test-Report.md` |
| Security / threat-model report | `Security-Threat-Model.md` |
| Performance / load test report and optimisation results | `Performance-Report.md` |
| Failure / recovery test report | `Failure-Recovery-Test-Report.md` |
| Costing document | `Cost-Report.md` |
| Timeline / Gantt chart | `Timeline.md` |
| Deployment documentation | `Deployment-Documentation.md` (runbook: `deploy/README.md`) |
| Final Jira dashboard and project report | this document |
| Requirements traceability | `Requirements-Traceability.md` |
| AI Engineering Log | `AI-Engineering-Log.md` |
