# Caf@IITK — AI Engineering Log

CS455 Software Engineering — Deliverable 1 (Document 4)

**Team XForce**
Krishna Kumayu (230576) · Kshitij Gupta (230581) · Rudransh Verma (230881) · Shashi Bhidodiya (230956) · Suryansh Verma (231061)

---

## Summary

### AI errors, hallucinations and risks identified
| # | Issue | Type | How found | Resolution |
|---|---|---|---|---|
| E1 | Misread which document the team meant (Doc 3 instead of the SRS) | Misinterpretation | Review of the AI's reply | Team redirected the AI |
| E2 | Wrong priority counts in Appendix B | Arithmetic error | Counting script | Corrected |
| E3 | FR-34 / FR-39 gaps (modification holds; refund retry) | Specification gap | Writing use-case extensions | FRs amended |
| E4 | PlantUML name collision merged an actor into a package | Diagram defect | Rendering and inspection | Aliases renamed |
| E5 | Activity-diagram step in the wrong swimlane | Diagram defect | Rendering and inspection | Fixed |
| E6 | Generator bug deleted three terms from RTM §6.1 | Tooling defect | Reading the output back | Patched |
| E7 | Agent granted INSERT-only yet shown performing an UPDATE (SD-6) | **Design contradiction** | Self-review of the SADD | Supersession moved to a `caf_app` job |
| E8 | Deployment diagram implied the DB runs on EC2 | Misleading diagram | Rendering and inspection | Redrawn |
| E9 | Render check reported the wrong exit code | Verification flaw | Noticed during checking | Strict re-check run |
| E10 | Markdown preview needed an unconfigured PlantUML server | Tooling gap | Error message | Local server + VS Code task |
| E13 | Agent role granted UPDATE, contradicting NFR-25 | **Design contradiction** | Cross-verification | Bookkeeping moved to `caf_app` |
| E14 | Data model missing columns/tables the text relies on | Incomplete design | Cross-verification | ER diagram completed |
| E15 | In-memory rate limits would break under multiple workers | **Design gap** | Cross-verification | Shared `rate_limits` table |
| E16 | Payment-failure response codes defined only in the SADD | Cross-document inconsistency | Cross-verification | Added to SRS §4.0 |
| E17 | RE-03 issue count stated approximately ("about 85") | Imprecise record | Counting script | Corrected to 82 |
| E18 | Registration's race path (two concurrent sign-ups with one email) was untested in the first version | Test gap | Coverage report | Test added before the PR was opened |
| E19 | Default JWT signing secret (17 bytes) was below the 32 bytes recommended for HS256, and nothing stopped production using it | **Security risk** | Library warning during the test run | Production startup refuses a default or short secret |
| E20 | The test for that check let an environment variable override the value under test | Test defect | Failing test run | Test passes the value explicitly |
| E21 | Inventory audit tests assumed `audit_log` is emptied between tests; it is append-only and is not | Test defect | Failing test run | Assertions scoped to the test's own entity |
| E22 | New CI jobs ran on every PR but did not block a merge, because the branch ruleset still required only the Jira-key check | Process gap | Reading the ruleset after the workflow was written | The three jobs were added as required checks |
| E23 | A code comment cited the wrong requirement number for item-disable proposals (FR-55 instead of FR-53) | Hallucinated reference | Checking the SRS before commit | Corrected |
| E24 | Slot-listing tests assumed timestamps come back with an IST offset; the API returns them in UTC | Test defect | Failing test run | Tests compare instants instead of text |
| E25 | A seat-count test contained an assertion that could never fail (it checked other slots when only one existed) | Test defect | Self-review before the PR | Assertion removed |

---

## Deliverable 2 entries

### Student self-registration (CAFIITK-126, US-01)

- **Asked for:** the `POST /auth/register` endpoint from the SRS (FR-1, US-01, password NFR) and the SADD API surface, with the three acceptance criteria as tests.
- **AI produced:** request schema (IITK-domain rule, lower-cased email, 8–128 character password, unknown fields forbidden), Argon2id hashing, a service that owns the transaction, a repository, and tests against real PostgreSQL. The tests cover the three acceptance criteria, case-insensitive duplicates and US-03 AC3 (`role=ADMIN` rejected).
- **How it was checked:** lint, strict type checking and the full suite against PostgreSQL 16 in a container. The coverage report showed the concurrent-duplicate path untested (E18), so a test was added. The PR was reviewed and approved by a teammate (Suryansh) with no change requests, then merged.
- **What changed:** the first version could not run its database tests because the author's machine had no Docker. The PR was held as a draft until Docker was installed and the tests had passed.
- **Outcome:** accepted.

### Login, token refresh, logout and account seed (CAFIITK-127, US-02)

- **Asked for:** login, logout, refresh-token rotation and token expiry (FR-4, FR-5, NFR-19), plus the deployment-time seed of the first Administrator and a Kitchen account (FR-2), as the team's sprint plan specified.
- **AI produced:** short-lived signed access tokens and opaque refresh tokens stored only as hashes. Refresh rotates the token on every use. One identical 401 for wrong password, unknown email and deactivated account. A current-user dependency and `/auth/me` for protected endpoints, an idempotent seed command run by Docker Compose after migrations, and tests for each acceptance criterion.
- **Design choices beyond the requirements:** replaying an already-rotated refresh token revokes all of that user's refresh tokens, following the SADD's token-theft threat (T3). An unknown email still costs one password verification, so response time does not reveal which emails are registered.
- **How it was checked:** lint, strict type checking and the full suite. A library warning in the test run exposed the short default signing secret (E19), and the first test of the fix was wrong (E20). An end-to-end run of the Docker Compose stack confirmed the seed and a real login. The PR was approved by a teammate (Kshitij) with no change requests, then merged.
- **What changed:** production now refuses a default or short signing secret. Login rate limiting (NFR-21) and audit entries for failed logins were left out of this PR and listed in it as follow-ups. Whether and when to schedule them is pending a team decision.
- **Outcome:** accepted.

### Set daily inventory (CAFIITK-136, US-11)

- **Asked for:** `PUT /admin/inventory/{date}/{item}` to set an item's prepared portions for a service date (FR-14), following the patterns of the already-merged catalogue and permission code.
- **AI produced:** an endpoint restricted to the Administrator through the shared permission check. It creates the row on first use and locks it for every change, refuses a total below the portions already allocated with 409 and no change (FR-15, also covering US-12 AC1–AC2), and audits each change with before and after counts in the same transaction. Tests cover validation, errors, permissions, the audit trail, eight concurrent first-time sets, and the database CHECK constraint.
- **How it was checked:** lint, strict type checking and the full suite, including teammates' tests. The first run failed on audit assertions (E21), and the concurrency test was repeated three times. The PR was approved by a teammate (Shashi) with no change requests, then merged.
- **What changed:** audit assertions were scoped to each test's own item rather than altering the shared test fixture. The PR noted two dependencies: a service date must be configured (US-14) before its inventory can be set, and the menu view itself belongs to US-10.
- **Outcome:** accepted.

### CI pipeline (CAFIITK-170)

- **Asked for:** the remaining CI jobs on top of the repo skeleton: lint, type check, tests with the 80% coverage gate, Flutter analyze, test and web build, and a secret scan.
- **AI produced:** three jobs beside the existing Jira-key check. Backend: lint, strict type checking and the test suite against PostgreSQL 16 in a container, with the coverage gate. Client: analyze, tests, an 80% line-coverage gate and the release web build, with Flutter pinned to the version the scaffold was created with. Secret scan: the full git history, using a release binary verified by checksum.
- **Design choices beyond the requirements:** the issue asked only for a backend coverage gate; a client gate was added because the project rule is 80% for both. The workflow also runs on pushes to `develop` and `main`.
- **How it was checked:** every step was run on the author's machine with the same commands as the workflow, after Docker and Flutter were installed for that purpose, and then on the PR itself. The PR was approved by a teammate (Kshitij) with no change requests, then merged.
- **What changed:** the AI pointed out that the new jobs would not block merges (E22), and the ruleset was updated. A side effect was that other open PRs could not merge until this one had.
- **Outcome:** accepted.

### Mock payment service, payment gateway and failed-payment tests (CAFIITK-148, US-23)

- **Asked for:** the separate mock payment service (FR-41) and the adapter the API uses to reach it, early enough for order placement to build on; later, the acceptance tests for US-23.
- **AI produced:** a service with authorise, void and refund and a configurable outcome (approve, decline, timeout, approve after a delay) that is not available in the production configuration. A gateway interface with an HTTP adapter, an in-memory fake for tests, and a guard that refuses any gateway call while a database transaction is open (NFR-6). Tests for the service, for the adapter over real HTTP, and for the guard against real PostgreSQL.
- **Design choices beyond the requirements:** every call is keyed by a caller-chosen reference, so a repeat returns the first result. Voiding a reference the service has not seen yet blocks a late approval. A timed-out or unreachable authorisation is returned as a timeout result rather than raised. The outcome control affects authorise only. These were listed in the PR for the reviewer.
- **How it was checked:** lint, strict type checking and the full suite, plus a manual run on the Docker Compose stack covering each outcome, the real 10-second timeout from inside the API container, and the production configuration. The PR was approved by a teammate (Rudransh) with no change requests, then merged. Order placement (CAFIITK-147) then used the gateway as delivered.
- **What changed:** for the second part, the AI found that releasing portions and the seat on a failed payment had already been implemented with order placement, so it wrote no release logic and added only acceptance tests: decline and timeout through the real payment path, inside the NFR-14 deadline, with the freed portion and seat then bought by another student. That PR was also approved by Rudransh with no change requests.
- **Known limits, stated in the PRs:** the acceptance tests use a 0.5-second payment timeout. A void queued after a timeout is written but not yet delivered, because the worker's outbox retrier is not built.
- **Outcome:** accepted.

### Browse today's menu (CAFIITK-135, US-10)

- **Asked for:** `GET /menu?date=` showing each ACTIVE item with its available portions and whether it can be ordered (FR-12, FR-13).
- **AI produced:** the endpoint, open to every logged-in role, and the orderability rule as a pure function. Tests against real PostgreSQL cover both acceptance criteria and the edge cases around them.
- **Design choices beyond the requirements:** an item that is both flagged and sold out reports unavailable. An item with no inventory set for the date shows zero portions rather than an error. A flag with an end time stops counting once that time has passed. The menu-opening time is not applied to browsing, because the SRS makes it a precondition of ordering. These were listed in the PR for the reviewer.
- **How it was checked:** lint, strict type checking and the full suite. A wrong requirement number in a comment was caught against the SRS before commit (E23). The PR was approved by a teammate (Rudransh) with no change requests, then merged. Order placement then reused the orderability rule.
- **Outcome:** accepted.

### Pick a pickup slot (CAFIITK-141, US-16)

- **Asked for:** `GET /slots?date=` with remaining seats and the bookable rule (FR-19), and the one-seat-per-order check (FR-20) once order placement existed.
- **AI produced:** the endpoint and the bookable rule as a pure function, with tests on a frozen clock that include the exact booking-close boundary. Later, a test that an order of three different items takes exactly one seat.
- **Design choices beyond the requirements:** a slot that is both closed and full reports closed. Exactly the booking-close interval before the start already counts as closed. A date with no service window returns an empty list. These were listed in the PR for the reviewer.
- **How it was checked:** lint, strict type checking and the full suite. Two test defects were found and fixed before the PRs were opened (E24, E25). Both PRs were approved by a teammate (Rudransh) with no change requests, then merged. Order placement then reused the bookable rule.
- **Outcome:** accepted.
