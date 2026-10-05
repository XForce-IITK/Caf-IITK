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
| E26 | The same audit-isolation mistake as E21 was repeated in the authorisation tests | Test defect | Failing test run | Assertions scoped to the test's own actor |
| E27 | An in-progress merge was cancelled by a stash taken to compare two test runs | Tooling mistake | Status check before committing | Merge redone from the committed state; no work lost |
| E28 | The SRS does not say whether a discount window includes its end time; the AI chose start-inclusive, end-exclusive without asking | Specification ambiguity | Writing the pricing engine | Flagged in the PR; team decision pending |
| E29 | Two simultaneous refreshes of one refresh token revoke all of the user's tokens, logging the user out | **Design risk** | Reproduced during code review | Pending; the client must make only one refresh call at a time (CAFIITK-177) |
| E30 | After the payment gateway was merged, the test setup loads settings before setting the test secret, so tests sign tokens with the short default key | **Test-validity regression** | Warning count rose from 1 to about 150 | Root cause identified; fix pending |
| E31 | US-04 AC1–AC2 and US-25 AC1–AC3 were proven on stand-in routes because the real endpoints did not exist yet | Verification gap | Planning | Real-endpoint tests assigned to CAFIITK-132, 153 and 147. Order placement now requires the key, but AC1–AC3 have not yet been repeated on it |

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

### Sprint 1 execution plan

- **Asked for:** an order of work for every open Sprint 1 ticket, before any code existed and with a same-day deadline.
- **AI produced:** a dependency-ordered plan: the skeleton first; then identity, catalogue, slots and pricing in parallel; then order placement; then the concurrency proof. Owners were taken from Jira, the critical path (CAFIITK-147) was flagged, and three acceptance criteria that depend on Sprint 2 features were noted.
- **How it was checked:** compared with the Jira backlog and the ticket dependencies.
- **Outcome:** accepted; used to sequence the sprint.

### Repository skeleton and core schema (CAFIITK-169)

- **Asked for:** the FastAPI and Flutter Web scaffold, Docker Compose and the first PR, following the SADD.
- **AI produced:** a module-per-area backend layout. Every table in SADD Figure 2.5 went into one Alembic migration, so that parallel feature PRs would not create conflicting migrations. It also produced a real-PostgreSQL test setup, the Flutter shell, a Compose stack (database, migrations, API, mock payment service) and a README.
- **How it was checked:** lint, strict type checking and the test suite. The migration was compared against the models with `alembic check`, and the Compose stack was started end to end. The PR was approved by a teammate (Suryansh) and merged.
- **What changed:** the generated migration was reviewed by hand and amended. The seed for the administrator-configurable parameters (SRS Table 4.0-B) was added, and the downgrade now drops the enum types.
- **Outcome:** accepted with modifications.

### Review of registration, CI and login (PRs #3–#5)

- **Asked for:** a review of three teammates' merged PRs.
- **AI produced:** a review that ran the suite and reproduced one real defect, where parallel use of a refresh token logs the user out (E29). It also listed lower-severity issues: the development signing secret is still short, the example seed password would become a real password if copied unchanged, login runs password hashing inside a database transaction, and CI reruns on PR title edits.
- **How it was checked:** the logout defect was reproduced with two simultaneous refresh requests.
- **Outcome:** findings recorded; fixes pending a team decision.

### Pricing engine and quote endpoint (CAFIITK-144, US-19)

- **Asked for:** the FR-24 pricing rules and `POST /quotes`, with the US-19 acceptance criteria as tests.
- **AI produced:** pricing as a pure function over integer paise (discount rules, subsidy with its percentage cap, rounding), kept separate from the database code so it can be unit tested. Also a repository, a service that converts the slot time to IST, and the endpoint. Tests cover all five acceptance criteria.
- **How it was checked:** lint, strict type checking and the full suite. The AC1 worked example was also calculated by hand. The PR was approved by a teammate (Suryansh) and merged.
- **What changed:** after the permission layer (CAFIITK-129) merged, the endpoint was switched to the shared permission check.
- **Outcome:** accepted. How discount windows are interpreted (E28) is pending team confirmation.

### Role-based authorisation (CAFIITK-129, US-04)

- **Asked for:** the SRS Table 4.1-A permission matrix and a reusable check for endpoints.
- **AI produced:** a permission list, a role-to-permission map and a `require_permission` dependency. On denial it returns 403 and writes a security audit entry. It also produced a shared audit-writing service.
- **How it was checked:** lint, strict type checking and the full suite. The first run failed on audit assertions (E26). The PR was approved by a teammate (Krishna) and merged.
- **What changed:** the ticket owner (Shashi) chose to read the role from the database rather than from the token, so a role change takes effect immediately. The owner also chose which fields a denial records (permission, method, path), and to prove AC1–AC2 on stand-in routes because those endpoints arrive in later sprints (E31). Real-endpoint tests are recorded on CAFIITK-132 and 153.
- **Outcome:** accepted with modifications.

### Onboard a menu item (CAFIITK-131, US-06)

- **Asked for:** `POST /admin/items` for the Administrator.
- **AI produced:** the endpoint, schema, service and repository, with validation of price limits, an audit entry for each new item, and tests for each acceptance criterion and for permissions.
- **How it was checked:** lint, strict type checking and the full suite. The PR was approved by a teammate (Krishna) and merged.
- **What changed:** the owner decided that item names must be unique, ignoring case, among active items only. A test that an onboarded item appears on the menu was deferred to CAFIITK-135, which builds the menu.
- **Outcome:** accepted with modifications.

### Configure the service window (CAFIITK-139, US-14)

- **Asked for:** `PUT /admin/service-days/{date}` to set a day's service window and generate its slots.
- **AI produced:** slot generation, which rejects a slot length that does not divide the window evenly. The slot length defaults to the configured parameter. The endpoint also has an audit entry, and tests cover the acceptance criteria, permissions and validation.
- **How it was checked:** lint, strict type checking and the full suite. The PR was approved by a teammate (Krishna) and merged.
- **What changed:** the owner set the reconfiguration policy. A day can be reconfigured only while no order references its slots; otherwise the request is refused with 409. The day's row is updated in place, so inventory already set for that day is kept.
- **Outcome:** accepted with modifications.

### Idempotency keys (CAFIITK-150, US-25)

- **Asked for:** reusable idempotency for create, modify and cancel requests (FR-32, NFR-7, NFR-18), ready for the order endpoints.
- **AI produced:** a service that claims the key inside the caller's transaction, so that a concurrent duplicate waits on the database and then replays the stored result. Reusing a key with a different request is refused, a duplicate that arrives while the original is still running gets 409, and keys expire after the configured period. Tests run on a stand-in order endpoint (E31).
- **How it was checked:** lint, strict type checking and the full suite. The concurrency test sends 20 simultaneous duplicates and expects one order. It was confirmed to fail, creating 20 orders, with idempotency disabled, and passed 11 of 11 runs with it enabled. During the branch update, an in-progress merge was lost and redone (E27). The PR was approved by the owner of order placement (Rudransh) and merged.
- **Outcome:** accepted. Repeating AC1–AC3 on the real order endpoint is still open.
