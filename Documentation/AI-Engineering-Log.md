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
| E29 | Two simultaneous refreshes of one refresh token revoke all of the user's tokens, logging the user out | **Design risk** | Reproduced during code review | The client now makes one refresh call at a time (CAFIITK-177); the server-side behaviour is unchanged |
| E30 | After the payment gateway was merged, the test setup loads settings before setting the test secret, so tests sign tokens with the short default key | **Test-validity regression** | Warning count rose from 1 to about 150 | Root cause identified; fix pending |
| E31 | US-04 AC1–AC2 and US-25 AC1–AC3 were proven on stand-in routes because the real endpoints did not exist yet | Verification gap | Planning | Real-endpoint tests assigned to CAFIITK-132, 153 and 147. Order placement now requires the key, but AC1–AC3 have not yet been repeated on it |
| E32 | The audit-isolation mistake of E21 and E26 was made a third time, in the order-placement tests | Test defect | Two tests passed alone and failed in the full suite | Assertions scoped to the test's own order |
| E33 | Order placement was first written with its own copies of the orderable and bookable rules and its own clock module, while two open PRs were adding the same rules and a different file at the same path | Duplication and merge-conflict risk | Reading the open branches before raising the PR | Clock module made identical to the teammates' file; branch rebased once their PRs merged and switched to the shared rules |
| E34 | FR-33 is listed on both CAFIITK-147 and CAFIITK-148; the AI implemented the release of holds on a failed payment under 147 while the owner of 148 had that story in progress | Scope overlap | Reading the sprint board before starting | Flagged to the author and in the PR; the owner of 148 then wrote acceptance tests only |
| E35 | The test harness first started the API as two workers sharing one listening socket; on Windows about a third of runs lost responses, although the orders had been accepted | Tooling defect | A test run that hung, then repeated runs with the database inspected | Each API process given its own port; requests alternate between them |
| E36 | The AI opened the order-placement PR without first showing its description to the author, after saying it would | Process lapse | Reported by the AI in its next summary | Description left editable; no change was requested |
| E37 | The AI created a Jira issue to satisfy the PR-title rule without asking the author | Process lapse | Questioned by the author | Kept by the author's decision; a release task now exists for every sprint |
| E38 | The AI reported twelve merged branches as still on the remote, reading stale local tracking references | Verification flaw | The author said the branches had been deleted | Checked against the remote; local references pruned |
| E39 | The AI stated that Sprint 3 held 25 issues; it held 23 | Arithmetic error | Summing the estimates | Corrected |
| E40 | The AI sent a batch of Jira changes that included closing a story the author had only asked to be reviewed | Process lapse | The author stopped the batch | Only the changes the author then named were applied |
| E41 | The generated client sends dates as date-times, which the backend rejects unless the time is midnight | Integration risk | Checking the format against the backend validator | A helper strips the time; documented in the README |
| E42 | Sprint 2 holds 73 points against 43 closed in Sprint 1, on AI-drafted estimates | **Planning risk** | Summing the estimates | Flagged in the sprint plan; reviewed and accepted by the team |
| E43 | While checking that the tests catch a broken route guard, the AI reverted an uncommitted file with a version-control command | Tooling slip | The next check found the old file | Rewritten from the same source; analysis, tests and coverage rerun |
| E44 | Formatting the whole client also reformatted the generated code, which would have failed the up-to-date check in CI | Tooling defect | Reading the commit's file list | The generation script now formats its own output |
| E45 | Tokens are kept in memory only, so reloading the page logs the user out; the SRS does not say where the client should keep them | Specification gap | Writing the session code | Flagged in the PR; the team accepted keeping tokens in memory only |
| E46 | The Sprint 2 plan assumed the agent tables, the agent's read views and its restricted database role already existed; no issue owned them, and three issues depended on them | **Planning gap** | Comparing the plan with the code | Built first, as its own PR under CAFIITK-164, with the proposal payload agreed in it |
| E47 | The check that the scheduled planning run had already happened that day compared a timestamp set by the database clock with the application clock | Defect | Failing acceptance test | The run's start time is now set from the application clock |
| E48 | The SRS makes disable and replenishment proposals expire when the service window opens, so one drafted during service would be expired from the start | Specification gap | Writing the agent's tools | During service the agent refuses them with the reason; flagged in the PR; team decision on the SRS pending |
| E49 | Test data written for the agent run prioritised an item that had no orders in the slot, which FR-54 does not allow; it passed only because nothing checked it yet | Test defect | The new output validator rejected it | Test data corrected so the tests check what they were written for |
| E50 | The LLM client has never called OpenAI, and its default model is an unconfirmed choice | **Verification gap** | No API key on the author's machine | Pending: one call with the team key, and a decision on the model |
| E51 | The Docker run of the heuristic fallback was abandoned when the image rebuild stalled downloading packages | Verification gap | The build did not finish | Behaviour covered by tests against PostgreSQL; the run before it had exercised the queue-to-worker path in Docker |
| E52 | The AI balanced the reassignment on open work rather than over the whole sprint, without asking which measure the author wanted, leaving the author 5 points above the others over the sprint | Planning misjudgement | Questioned by the author | Two issues reassigned; whole-sprint totals within 3 points |
| E53 | The AI said the merges were probably blocked because the approval was given while the PR was a draft; the next retry worked without any change | Misdiagnosis | The author pointed out it did not fit #28 | Retracted |
| E54 | The AI said 27 requirement tasks could be closed; its own table listed 29 | Arithmetic error | Counting the transitions made | Corrected in the report |
| E55 | A background wait for CI used a `gh` option this version does not have, so it could never finish | Tooling defect | Noticed while merging by hand | Stopped; later waits checked differently |
| E56 | For an order that does not exist, cancel and modify log a security event while tracking does not | Design inconsistency | Reading the merged cancel and modify code | Flagged in the PR; team decision pending |
| E57 | In the first version of cancel, the 404 path read the Student's account after the transaction had rolled back. That silently opened a new transaction, so writing the security event failed | Implementation defect | The new 404 tests failed | The Student's id and role are read before the transaction; tests pass |
| E58 | The client generator script deletes the generated client before generating it, so when it failed on an out-of-date local Flutter SDK it left the client deleted | Tooling defect | The working tree showed the generated files deleted | Files restored from git, local Flutter pinned to the CI version, then regenerated. The script itself is unchanged |
| E59 | Cancel refunded only against the order's first payment authorisation. mockpay refuses a refund larger than one authorisation, so after a price-raising modify a full cancel would have stayed PENDING | **Design gap** | Designing modify, then shown against real mockpay with a deliberately broken split | Refunds are split across the order's authorisations, oldest first; test against real mockpay |
| E60 | Re-pricing an order for a modify counted the order itself as "another subsidised order today", so it would lose its own subsidy | **Specification gap** (FR-24 step 4 does not cover re-pricing) | Reading the pricing code before writing modify | The order being re-priced is excluded from the check; test added |
| E61 | While deliberately breaking code to check that tests fail, the AI reverted a change with `git checkout`, which also discarded an uncommitted change in the same file | Process error | Caught by `git diff` straight after | Change re-applied and verified; later checks restore from backup copies, never from git |
| E62 | Settling a price-raising modify that moves the order to another slot locked the slots out of the canonical order (through the foreign-key check on `orders.slot_id`), so opposite moves could deadlock. Merged in #44 | **Concurrency defect** | The US-30 AC4 mixed workload reported 1–2 deadlocks per run; the PostgreSQL log showed the cycle | Both slots locked in ascending id order; a regression test that deadlocked on every run before the fix; 0 deadlocks after (#54) |
| E63 | An intermittent failure of the US-30 AC1 rush test ("server closed the connection") was first put down to machine load before there was evidence | Unverified attribution | The author asked what caused it and whether it was safe | Investigated with container and Docker logs: no crash, out-of-memory or restart found. Cause still unknown; reported as such in #39 |
| E64 | The core schema sized `menu_items.unavailable_source` at 20 characters, but FR-53 records an approving proposal's ID (36 characters) there | Schema defect | Noticed while building the flag endpoint (CAFIITK-134) | Flagged in #33; widened by migration 0003 in #43 |
| E65 | The SRS does not define the kitchen's "current slot", an order's confirmation time, or whether READY orders count in the item totals; the AI chose all three without asking | Specification ambiguity | Writing the kitchen queue | Listed for the reviewer in #35; approved without change |
| E66 | The chosen current-slot rule (earliest slot not yet ended) dropped a slot's READY orders as soon as it ended, so a no-show, allowed only after the grace period, could never be made from the client | **Design defect** | The AI noted the risk after #35 but fixed it only when adding the transition buttons | Queue gained `earlier_slots` (today's ended slots with open orders), with a test (#55) |
| E67 | The proposal-decisions PR stated that the format check was clean; it had not been rerun after the migration was added, and CI failed on it | **Verification flaw** (incorrect test evidence) | CI | File formatted and pushed; the AI told the author the claim had been wrong. The PR text was not edited |
| E68 | The SRS gives no status code for an approval that fails re-validation and does not say when stale proposals expire if the worker is down; the AI chose 409 and expiry when the list is read | Specification ambiguity | Writing the decision endpoints | Listed for the reviewer in #43; approved without change |
| E69 | The concurrent-decision test left its rows in the database, so the next test failed on a duplicate service day | Test defect | Failing test run | Test given the clean-up fixture |
| E70 | Two client defects in the staff dashboards: the kitchen and run-history pollers kept a timer running after their screen closed, and after a refresh an order's error message could show under a different order | Implementation defect | Widget tests, before the PR | Timers cancelled when the screen closes; slot cards and orders keyed by ID |
| E71 | #35, #43, #47, #50 and #55 were not tried by hand against the running Docker Compose stack; each PR says so | **Verification gap** | Stated in each PR | Pending: an end-to-end walkthrough before the D2 release |
| E72 | For CAFIITK-134 the AI merged `develop` into the branch before merging, instead of rebasing as the revised sprint plan's rule 5 asks | Process lapse | The AI noticed when reading the revised plan | Later PRs rebased just before merge |

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

### Place an order (CAFIITK-147, US-22)

- **Asked for:** the author's Sprint 1 tickets, completed with the safest available method and the team's branch, PR and review procedure. This was the first of them: `POST /orders` (FR-29, FR-30, FR-33).
- **AI produced:** order placement as reserve, authorise, confirm. One transaction locks the inventory rows and then the slot, re-checks availability, re-prices against the quoted amount, allocates the portions and one seat, and commits the order awaiting payment with its first price snapshot and audit entries. The payment gateway is called with no transaction open. A second transaction accepts the order, or marks it failed and returns its holds. Also the order state table (SRS Table 4.6-A) as a pure function that carries each transition's effect on portions and seat, a bounded retry for deadlocks, and tests for the three acceptance criteria and the paths around them.
- **Design choices beyond the requirements:** the Student's own account row is locked first, outside the documented lock order, so that two simultaneous orders cannot both take the day's subsidy. The idempotency key is completed in the reserve transaction, so a repeat returns the same order even while payment is in flight, and a rejected request does not use up its key. A removed, flagged or sold-out item gives 409 naming it, while an item that never existed gives 422. The quote service was split so that an order is priced by the code that produced the quote. These were listed in the PR for the reviewer.
- **How it was checked:** lint, strict type checking and the full suite against PostgreSQL 16 in a container. The author's machine had no Docker at first, so the code was left uncommitted until Docker was installed and the tests had run. The first full run failed on audit assertions (E32). Before the PR was raised, the NFR-1 rush was run against the endpoint with the harness below. The PR was approved by a teammate (Suryansh) with no change requests, then merged.
- **What changed:** the AI found the overlap with CAFIITK-148 (E34) and the duplicated rules (E33) and raised both before the PR. The PR itself was opened without the promised preview (E36).
- **Known limits, stated in the PR:** the per-student limit on active orders (US-26), the hold-expiry sweeper and the outbox worker are not built. Of the idempotency criteria noted in E31, the repeat and the different-cart cases are now tested on the real endpoint; the 20-concurrent-duplicates case is not.
- **Outcome:** accepted.

### Concurrency test harness (CAFIITK-172)

- **Asked for:** the PostgreSQL test harness and load-generation script that prove NFR-1, NFR-2, NFR-4 and NFR-5 under the menu-release rush.
- **AI produced:** a test fixture that starts two API processes and the mock payment service as real processes on the test database, and a load generator that seeds one item, one slot and one Student per request, sends all orders at once, and compares both the responses and the database with the only correct outcome. The same file runs as a script against the Docker Compose stack and fails on any violation.
- **How it was checked:** tests at a small scale, including that the checker reports an oversold counter and an unexpected response. An intermittent hang in the first version was investigated rather than rerun: the database showed every connection idle and no lock waits, one worker gave 24 clean runs of 24, and two workers on a shared socket lost responses (E35). The full rush then passed 10 runs of 10. The suite also passed on the CI runners. The PR was approved by a teammate (Suryansh) with no change requests, then merged.
- **What changed:** each API process now has its own port. The harness also ran into E30: a separate server process read the environment's signing secret while the tests signed with the cached default. The fixture passes the secret the tests actually use; the import order behind E30 was left as it was and described in the PR.
- **Outcome:** accepted.

### The rush never oversells (CAFIITK-155, US-30) — AC1 and AC2

- **Asked for:** the acceptance tests for US-30.
- **AI produced:** AC1, 200 concurrent orders for 50 portions and 30 seats across two API processes, 10 consecutive runs, each required to give exactly 30 accepted orders, 170 refusals, 20 portions and no seats left. AC2, five direct database writes that would oversell or go negative, each refused by a CHECK constraint with the row left unchanged. No application code changed.
- **How it was checked:** the full suite locally and on the CI runners. The PR was approved by a teammate (Suryansh) with no change requests, then merged.
- **What changed:** the AI reported that AC3 and AC4 need the modify and cancel endpoints, which are Sprint 2 work, and offered three ways forward. The author chose to deliver AC1 and AC2 now and carry the other two into Sprint 2 rather than pull that work forward. AC3 and AC4 are in the suite as skipped tests with the reason. The AI read the ticket's wording of AC2 ("a portion count of 0 ... set it to 1") as "allocate one more than exists" and said so in the PR.
- **Outcome:** accepted for AC1 and AC2. The story stays open.

### Portions follow the order lifecycle (CAFIITK-138, US-13) — AC1 and AC2

- **Asked for:** the acceptance tests for US-13.
- **AI produced:** AC1, ordering 2 of 10 leaves 8 while the order awaits payment, observed from inside the payment call, and still 8 once accepted. AC2, a declined payment returns the 2 portions with no further action. No application code changed; the behaviour was delivered with order placement.
- **How it was checked:** the full suite locally and on the CI runners. The PR was approved by a teammate (Suryansh) with no change requests, then merged.
- **What changed:** AC3 and AC4 cancel an order and were carried into Sprint 2 by the same decision as for US-30. They are in the suite as skipped tests with the reason. The rule they will test is already in the state table: cancelling an accepted order returns portions and seat, cancelling one in preparation returns only the seat.
- **Outcome:** accepted for AC1 and AC2. The story stays open.

### Sprint 2 planning and Jira set-up

- **Asked for:** a review of the board for statuses that had fallen behind the code; assignment of the Sprint 2 issues in the pattern of Sprint 1, keeping an issue and the issues it depends on with one member where possible; then estimates, dependency links, priorities and a per-member order of work.
- **AI produced:** an assignee and story points for every Sprint 2 issue, rough points for Sprints 3 and 4, 29 "blocks" links between Sprint 2 issues, priorities re-ranked so that an issue which blocks others ranks above the issues it blocks, a release task in each sprint for the merge from `develop` to `main`, and a Sprint 2 plan with a staged order of work and a hand-off table.
- **How it was checked:** each proposal was shown to the author before it was applied. Suggested status changes were compared with the merged tests in the repository, and values written to Jira were read back.
- **What changed:** one story was moved between members to even out the load. The AI first suggested closing US-12 as already delivered, then on a second look found that no PR carried its key and that its tests did not follow the naming convention; the author left it open. Several errors were made along the way (E37 to E40, E42).
- **Outcome:** accepted by the author and applied in Jira.

### Generated API client (CAFIITK-176)

- **Asked for:** a Dart API client generated from the backend's OpenAPI schema, with CI failing when the committed client is out of date (NFR-39).
- **AI produced:** a command that exports the schema with sorted keys, a script that regenerates the client from it, the generated client itself, a CI step that regenerates both and fails on any difference, and providers through which the app reaches the client. Generated code is excluded from static analysis and from the client coverage gate.
- **Design choices beyond the requirements:** operation IDs were changed to the endpoint function names so that client methods have readable names, with a backend test that the names stay unique. A pure-Dart generator was chosen so that CI needs no further toolchain.
- **How it was checked:** lint, strict type checking, the new export tests, the client tests and the release web build on the author's machine, and a repeat generation from a clean cache that gave identical output. The full backend suite and the new CI step ran on the CI runners and passed. The PR was approved by a teammate (Shashi) with no change requests, then merged.
- **What changed:** the date format the client sends was checked against the backend's validator and a helper added (E41). The script was later made to format its own output (E44).
- **Outcome:** accepted.

### Login, role-based routing and interceptors (CAFIITK-177)

- **Asked for:** login and register screens, a redirect to exactly one dashboard per role (FR-5), and interceptors for token refresh, a request ID, an idempotency key per user action and retry with the same key (NFR-18).
- **AI produced:** the two screens with client-side validation; a session holder with login, register, logout and a single shared refresh call; a route guard that keeps each role in its own dashboard and logged-out users on login and register; the interceptors; and placeholder dashboards for the three roles. Retries apply only to requests that carry an idempotency key, on a network failure or a 502, 503 or 504.
- **Design choices beyond the requirements:** CORS configuration was added to the backend, because a browser client cannot call the API without it; any localhost port is allowed outside production and only configured origins in production (NFR-27). The single shared refresh call addresses E29 on the client side.
- **How it was checked:** 44 client tests against a scripted stand-in for the API, including the first two acceptance criteria of US-02 for each role; the route guard was deliberately broken to confirm that the tests fail (E43). CI passed, including the full backend suite. The author then ran the flow by hand in Chrome and Firefox against the local stack, including a token refresh after the access-token lifetime. The PR was approved by a teammate (Shashi) with no change requests, then merged.
- **What changed:** nothing after the manual run. Where the client should keep its tokens is an open question (E45).
- **Outcome:** accepted.

### Student order flow, first half (CAFIITK-178)

- **Asked for:** the Student dashboard for the endpoints that already exist: menu with availability, slot picker with remaining seats, the full price breakdown before confirming, and placing the order (NFR-32).
- **AI produced:** one screen with those four steps. A refused order names the item or slot that was unavailable; a changed price is shown and must be confirmed again (FR-26); a failed payment keeps the cart. Each priced quote gets its own idempotency key, reused if that confirmation is repeated.
- **How it was checked:** 64 client tests in all, with analysis, the coverage gate and the release web build on the author's machine. The author then ran the flow by hand against the local stack: ordering, a declined payment, and a confirmation repeated across an API outage, which reached the server once the API returned and carried the same key as the failed attempts. The PR was approved by a teammate (Shashi) with no change requests, then merged.
- **What changed:** an earlier login test was corrected, because the dashboard now loads data as soon as it opens.
- **Outcome:** first half accepted. The story stays open: modify, cancel and order tracking wait for endpoints owned by other members.

### Agent schema and proposal format (CAFIITK-164, first part)

- **Asked for:** the database pieces the Sprint 2 agent and proposal issues all depended on (E46), ahead of the agent run itself.
- **AI produced:** a migration with the agent tables of SADD Figure 2.6 (runs, tool-call and LLM-call logs, proposals); five read views that give the agent item and slot totals only, with no student identifiers; a `caf_agent` database role that may read those views and insert proposals and logs, and nothing else (NFR-25); a database rule allowing one planning run at a time (FR-50); and the payload format for each proposal type, shared with the proposal-approval and kitchen-queue issues.
- **How it was checked:** lint, strict type checking and the full suite; the migration compared with the models, downgraded and re-applied. The role's privileges were tested by running statements as `caf_agent` against PostgreSQL. The PR was approved by a teammate (Suryansh) with no change requests, then merged.
- **What changed:** nothing after review. The kitchen queue (CAFIITK-158) was then built on the payload format as agreed.
- **Outcome:** accepted.

### caf-worker (CAFIITK-174)

- **Asked for:** the background process of SADD ADR-07: one codebase run in worker mode, with exactly one worker running jobs at a time.
- **AI produced:** a scheduler that runs jobs only while it holds a PostgreSQL advisory lock; other workers wait and take over if the leader stops. A leader that loses its lock connection stops and exits so Docker restarts it. Jobs are registered in one list, can also run at start-up, and a failing run does not stop its job. Docker Compose gained the worker service.
- **How it was checked:** tests against PostgreSQL with two workers, a stopped leader, a killed database session and the real worker process; repeated runs to check for flakiness; and two worker containers in Docker Compose, where stopping the leader made the other take over. The PR was approved by two teammates (Shashi and Suryansh) with no change requests, then merged.
- **What changed:** nothing after review.
- **Outcome:** accepted.

### LLM client (CAFIITK-175)

- **Asked for:** the backend-only LLM client of SADD 2.3, with a timeout, a circuit breaker, the daily request cap and a cache. The team chose OpenAI, as named in the proposal.
- **AI produced:** a client that refuses to call while a database transaction is open (NFR-6), answers a repeated identical request from a per-day cache, stops calling for a while after repeated failures, and counts every call against the daily cap in the database so the cap holds across processes (NFR-13, NFR-42). Every failure becomes one "LLM unavailable" signal for the fallback. The API key is read from the environment and never logged; without it the agent uses only the heuristic. Tests use a scripted stand-in, so CI needs no key.
- **How it was checked:** tests against PostgreSQL, including 12 concurrent callers against a cap of 5, and tests of the OpenAI adapter over a mocked connection, including that the key never appears in an error. The PR was approved by a teammate (Suryansh) with no change requests, then merged.
- **What changed:** nothing after review. It has not yet been run against OpenAI itself (E50).
- **Outcome:** accepted.

### Planning agent run (CAFIITK-164, US-39)

- **Asked for:** the agent run of SADD SD-6: scheduled before service and on demand, one at a time, with every tool call and LLM request logged and nothing identifying a student sent to the LLM.
- **AI produced:** a run that reads the five views as `caf_agent`, computes the report's demand summary and stock-out forecast, then lets the LLM use eight whitelisted tools: five read tools and three that draft proposals. Drafted proposals are stored as pending with their expiry. An unknown tool is refused and recorded as a security event (FR-60). The API only queues a run; the worker runs it, so a slow LLM cannot hold up the API (NFR-17). Endpoints list runs and show each run's report, proposals and tool-call log.
- **Design choices beyond the requirements:** the forecast's numbers are computed by code from the tool data, and the LLM supplies only the judgement: which proposals to draft and why. The read tools take no arguments, so the model cannot widen what it reads. Both were flagged in the PR and approved without comment.
- **How it was checked:** 34 tests against PostgreSQL with a scripted LLM, including the three acceptance criteria, one of which checks that no student's name, email or ID appears in anything sent to the LLM. In Docker Compose, a run queued through the API was executed by the worker container, and a second request got 409 with the running run's ID. A test found one defect (E47), and a gap in the SRS was handled and flagged (E48). The PR was approved by a teammate (Suryansh) with no change requests, then merged.
- **What changed:** after other members' PRs merged, the generated client conflicted; it was regenerated from the combined backend instead of being merged by hand.
- **Outcome:** accepted.

### Planning without the LLM (CAFIITK-168, US-43)

- **Asked for:** a usable briefing when the LLM is down, slow or over its daily cap (FR-59), and reuse of an earlier result when the data has not changed (FR-64).
- **AI produced:** a rule-based planner, used when the LLM cannot be used or a run exceeds its limits. It drafts the same proposal types from the same forecast: extra portions for an item likely to run out, disabling it if even the maximum would not be enough, and the order of preparation for the next slot. Its proposals go through the same tools as the LLM's, so they are checked and expire in the same way. The run is marked as heuristic, with the reason. A run whose data matches an earlier successful run of the same day reuses that result without an LLM request.
- **How it was checked:** tests against PostgreSQL for the three acceptance criteria: an unreachable OpenAI endpoint gives a heuristic report in under 5 seconds while the menu still answers in under a second; a reached cap sends no request to the LLM; identical data reuses the earlier run. The Docker run was not repeated (E51). The PR was approved by a teammate (Shashi) with no change requests, then merged.
- **What changed:** two earlier tests that expected a failed run without an LLM now expect a heuristic run.
- **Outcome:** accepted.

### Checking the agent's output (CAFIITK-167, US-42)

- **Asked for:** filtering of invalid or invented proposals before an Administrator sees them (FR-58).
- **AI produced:** a validator that discards a proposal naming an item that does not exist or is not active, prioritising an item with no orders in the slot, or adding more portions than the configured maximum or the 500-portion limit. The reason is logged and sent back to the model. The model gets one retry after bad output; after that the rule-based planner takes over. The rule-based planner's own proposals go through the same validator.
- **Design choices beyond the requirements:** the log separates malformed output from well-formed output that fails these checks, so a reader can tell the two apart. Flagged in the PR and approved without comment.
- **How it was checked:** tests against PostgreSQL for the three acceptance criteria (an invented item, invalid output twice, and 10,000 extra portions) and for each validation rule. The validator also caught a defect in earlier test data (E49). The PR was approved by a teammate (Shashi) with no change requests, then merged.
- **What changed:** the earlier test data was corrected.
- **Outcome:** accepted.

### Order tracking endpoint (CAFIITK-154, US-29)

- **Asked for:** `GET /orders/{id}` with the order's current status and its timestamped history (FR-40), started as soon as it was unblocked.
- **AI produced:** the endpoint, a tracking service that owns its read transaction, two repository reads, response schemas, and the regenerated Dart client. Another Student's order answers 404 exactly like a missing one and is logged as a security event (FR-7), which also delivered US-05 AC1.
- **How it was checked:** the full backend suite against PostgreSQL 16 in a container (433 passed), lint, strict type checking and the client tests. The kitchen transitions did not exist yet, so the tests applied them through the state machine directly, writing the same rows the kitchen endpoint will; the PR flagged them for replacement once that endpoint exists. The PR was approved by a teammate (Rudransh) with no change requests, then merged.
- **Outcome:** accepted.

### Student order flow, second half (CAFIITK-178): tracking, cancel and modify

- **Asked for:** the rest of the Student flow as each backend endpoint landed: the order's live status, cancelling, and changing its items or slot.
- **AI produced:** three PRs.
  - Tracking: a status panel refreshed every P-POLL, which stops at a final state or when the order leaves the screen.
  - Cancel: a confirmation that says what is refunded, sent at the order version shown.
  - Modify: an editor that starts from what the order holds, keeps the order's own portions and seat available to it, is priced before confirming, and is applied at the version shown.
  - In all three, refusals are explained, and a network failure keeps the idempotency key so a repeat is safe.
- **How it was checked:** the client tests grew to 97, line coverage stayed above 97% and the release web build passed. In each PR one key test was confirmed real by breaking the rule it guards in a backed-up copy of the file, seeing the test fail, and restoring the file. The first two PRs were approved by a teammate (Rudransh) and the third by another (Shashi), with no change requests, then merged. Not yet checked by hand in a browser.
- **What changed:** each branch had to be brought up to date with `develop` before it could merge, because teammates' PRs landed in between.
- **Outcome:** accepted; the story is complete.

### Private orders (CAFIITK-130, US-05)

- **Asked for:** close US-05 once modify existed.
- **AI produced:** no application code. Reading the merged code showed the behaviour had already been delivered and tested under three other stories, so the AI added one acceptance test named for US-05 AC2 that covers modify and cancel together.
- **How it was checked:** the full backend suite (653 passed). The PR was approved by a teammate (Shashi) with no change requests, then merged.
- **Outcome:** accepted.

### Sprint 2 reassignment and board clean-up

- **Asked for:** redistribute an unavailable member's five issues so the other four had about the same workload, with as few cross-member dependencies as possible and without moving anyone else's issues; then revise the sprint plan; later, close any backlog requirement tasks that the merged work had satisfied.
- **AI produced:** a reassignment, a revised sprint plan, and a review of every open requirement task against the acceptance tests on `develop`.
- **What changed:** the AI first balanced on open work only, which put most of the reassigned work on the author. The author asked for the whole sprint to be balanced instead, and two issues were moved again (E52). Of the requirement tasks, 29 were moved to Done; four were left for their owners to confirm, and the rest were listed with what each still needs.
- **Outcome:** accepted by the author and applied in Jira.

### Cancel an order (CAFIITK-153, US-28)

- **Asked for:** `POST /orders/{id}/cancel` with the right refund and resource effects (FR-21, FR-37, FR-39). Following the team's branch, PR and review rules.
- **AI produced:**
  - One transaction checks ownership, state, the cut-off and the order version. It applies the cancel through the order state machine, and writes exactly one refund record (backed by the partial unique index). The refund is sent to the payment gateway only after commit.
  - A stale version gets 409 with the new state and the refund that would now apply, so the Student can confirm again.
  - Another Student's order gets 404 and a security event. Kitchen Staff get 403, which also closed US-04 AC2.
  - The regenerated Dart client.
- **How it was checked:**
  - 17 tests against PostgreSQL, including concurrent cancels and a refund that mockpay does not acknowledge. The full suite was run several times.
  - One intermittent failure, in the US-30 rush test, was investigated at the author's request rather than rerun until it passed (E63).
  - Rebased three times as teammates' PRs merged; the generated client was regenerated each time rather than merged by hand.
  - The PR was approved by a teammate (Suryansh) with no change requests, then merged.
- **What changed:** E57 was fixed before the PR. E58 occurred while regenerating the client.
- **Known limits, stated in the PR:** no job yet retries refunds left PENDING; refunds after a modify needed more work (later E59).
- **Outcome:** accepted.

### Portions follow the order lifecycle (CAFIITK-138, US-13) — AC3 and AC4

- **Asked for:** the two acceptance tests carried over from Sprint 1, now that cancel exists.
- **AI produced:** two tests. Cancelling an accepted order of two returns both portions; cancelling one in preparation returns none. The kitchen endpoint was not merged yet, so preparation was reached through the state machine, as the plan allows.
- **How it was checked:** the full suite. The AC4 test was shown to be real by temporarily making the state machine return portions from preparation: the test failed, and the change was reverted. The PR was approved by a teammate (Suryansh) with no change requests, then merged.
- **Outcome:** accepted; the story is complete.

### Modify an order (CAFIITK-152, US-27)

- **Asked for:** `PATCH /orders/{id}`: change items and/or slot atomically before the cut-off, re-price, and settle the difference (FR-35, FR-36, FR-39).
- **AI produced:**
  - The same reserve, authorise, confirm pattern as placement. One transaction takes only the extra portions and the new seat while the old ones are still held, re-prices, and records the modification as holding.
  - A lower or equal price is applied in that transaction, with exactly one refund of the difference.
  - A higher price is charged with no transaction open, then applied, or fully released if the payment is declined or times out.
  - A read-only endpoint that prices a change before the Student confirms it.
  - The regenerated client.
- **Design choices beyond the requirements, listed in the PR:**
  - A changed order is recorded in its history as an ACCEPTED → ACCEPTED transition.
  - A slot on another day, or a request that changes nothing, gets 422.
  - A declined difference gets 402.
- **How it was checked:**
  - 32 tests, including one against real mockpay.
  - Three deliberate breakages, each caught by the matching test: the subsidy exclusion removed, refunds not split, holds not released after a decline.
  - Error-path tests were added when router coverage dropped to 79 %.
  - The PR was approved by a teammate (Shashi) with no change requests, then merged.
- **What changed:** E60 and E59 were found and fixed before the PR; E59 also changes how cancel sends refunds. E61 occurred during the breakage checks. E62, a lock-order defect, was found later and fixed in #54.
- **Known limits, stated in the PR:** the sweeper that releases a modification's holds after a crash, and the retrier for unacknowledged refunds and voids, are not built.
- **Outcome:** accepted; follow-up fix #54 approved by a teammate (Suryansh), merge pending.

### The rush never oversells (CAFIITK-155, US-30) — AC3 and AC4

- **Asked for:** the two acceptance tests carried over from Sprint 1, and an extended load generator.
- **AI produced:**
  - **AC3:** on 30 orders, a modify and a cancel arrive together at different API processes. Exactly one of each pair must succeed, and the database must match the winner. Half the modifies take the payment path, half the refund path.
  - **AC4:** a 60-second random workload of place, modify and cancel by 40 Students across both processes. No server errors are allowed, and afterwards every counter must equal what the orders hold. PostgreSQL's deadlock count is reported.
  - The load generator gained both, plus a command-line option for the Docker Compose stack.
- **How it was checked:** two deliberate breakages, each caught by the matching test: cancel ignoring the version, a modify keeping its old seat. The full suite was run. The PR was approved by a teammate (Suryansh) with no change requests, then merged.
- **What changed:** the deadlock count in AC4 later exposed E62.
- **Outcome:** accepted; the story is complete.

### Move orders through the kitchen (CAFIITK-159, US-34)

- **Asked for:** the kitchen's Start, Ready, Picked Up and No-show transitions (FR-29, FR-43). Reassigned to the author when the sprint was revised.
- **AI produced:**
  - `POST /kitchen/orders/{id}/transitions` for Kitchen Staff and the Administrator, applied through the order state machine.
  - Any other move gets 409 and changes nothing.
  - A no-show is refused until the grace period after the slot has passed; when allowed it refunds nothing and restores nothing.
  - Every move is recorded with the staff member as actor and bumps the order version.
  - The regenerated client.
- **How it was checked:**
  - 12 tests, including one that a Student cancelling from an older view is told the order is now in preparation.
  - Two deliberate breakages, each caught by the matching test: the grace check removed, a no-show releasing resources.
  - The PR was approved by a teammate (Suryansh) with no change requests, then merged.
- **What changed:** before the PR, the AI checked the open kitchen-screen PR (#50) for any request shape it assumed; there was none. The time a no-show becomes allowed is reported in IST, like other service times.
- **Outcome:** accepted.

### Slot lock order in modify (CAFIITK-152 follow-up, #54)

- **Asked for:** the AC4 workload failed once and reported deadlocks while 159 was being verified. The author had earlier asked that failures be diagnosed and explained before moving on.
- **AI produced:** the cause, from the PostgreSQL log (E62). It wrote a test that reproduced the deadlock on every run *before* changing the code, then made the fix: settling locks both slots in ascending id order.
- **How it was checked:** the regression test, 3 passes of 3 after the fix. The AC4 workload reported 0 deadlocks in 2 runs of 2, against 1–2 per run before. Full suite run. The PR was approved by a teammate (Suryansh) with no change requests.
- **Outcome:** pending merge.

### Flag an item temporarily unavailable (CAFIITK-134, US-09)

- **Asked for:** `POST` and `DELETE /items/{id}/flag` with a reason (FR-11, FR-12): the item stops being orderable, while portions and orders already placed are untouched.
- **AI produced:**
  - Both endpoints for Kitchen Staff and the Administrator; a Student gets 403, an unknown item 404, an item that is not ACTIVE 409.
  - Only the flag columns change. The menu and order placement already honoured the flag, so a flagged item shows as unavailable and new orders for it get 409.
  - Audit rows with the state before and after, in the same transaction.
  - The item row is locked `FOR NO KEY UPDATE`: order placement holds a key-share lock on the item through `order_lines`, so a plain `FOR UPDATE` would make flagging wait for orders in flight.
  - The regenerated client.
- **How it was checked:** 18 tests, including the three acceptance criteria and the lock choice; the full backend and client suites. The PR records a manual check against Docker Compose. `develop` was merged in and CI rerun before merging (E72). The PR was approved by a teammate (Suryansh) with no change requests, then merged.
- **What changed:** nothing after review. E64 was found here and handed to CAFIITK-165.
- **Outcome:** accepted.

### Kitchen queue (CAFIITK-158, US-33)

- **Asked for:** `GET /kitchen/queue` for the current and next slot (FR-42), with AC2 reading an approved prep-priority proposal from the proposals table (FR-54). Reassigned to the author when the sprint was revised.
- **AI produced:**
  - A kitchen module: ACCEPTED, PREPARING and READY orders of the two slots, sorted by slot start, then confirmation time.
  - Per-slot item totals, ordered by a pure function: the approved list first, then items it does not name by count; descending count when there is no approved proposal or its payload is malformed.
  - The regenerated client.
- **How it was checked:** 7 tests against PostgreSQL, covering both acceptance criteria, a superseded approval, a pending proposal that must be ignored, and a malformed payload; 100% coverage of the module; the full suites. The PR was approved by a teammate (Kshitij) with no change requests, then merged.
- **What changed:** the open questions of E65 were listed in the PR for the reviewer. One of those choices turned out wrong (E66) and was corrected under CAFIITK-179.
- **Outcome:** accepted; the current-slot rule was later extended (#55).

### Approve or reject the agent's proposals (CAFIITK-165, US-40)

- **Asked for:** `GET /admin/proposals` and approve and reject through `ProposalService` under the Administrator's identity (FR-53 – FR-57, UC-25, UC-26). Started once the agent run (CAFIITK-164) was merged.
- **AI produced:**
  - Approve locks the proposal, expires it if its target start has passed or a newer one superseded it, re-validates it (FR-57), then applies it, marks it APPROVED and writes the audit rows in one transaction. The change runs inside a savepoint, so a failed re-validation leaves nothing half-applied and marks the proposal INVALIDATED.
  - Reject requires a reason. A proposal that cannot be decided answers 409 with its resulting status (E68).
  - Superseding is done on the decision side, because the agent's role can only insert rows (consistent with E7 and E13).
  - A worker job that expires stale proposals without blocking an Administrator who is deciding one.
  - Migration 0003 for E64, and the regenerated client.
- **How it was checked:**
  - 20 tests, including all six acceptance criteria. AC6 approves through the API, then reads the kitchen queue. Also a savepoint rollback, superseding, and a concurrent approve and reject.
  - The migration was upgraded, downgraded and upgraded again on PostgreSQL 16, with a single head.
  - The full suites. CI caught E67; E69 was fixed before the PR.
  - At the author's request the AI explained the migration-announcement and rebase rules before merging. The branch was rebased three times as teammates' PRs merged.
  - The PR was approved by two teammates (Rudransh and Suryansh) with no change requests, then merged.
- **Outcome:** accepted.

### The agent cannot act beyond its authority (CAFIITK-166, US-41)

- **Asked for:** the US-41 acceptance tests (FR-60, FR-61, NFR-25). AC3 needed only the database role; AC1 and AC2 waited for the agent run.
- **AI produced:** tests only, through the real agent with a scripted model:
  - AC1: five unregistered tools that would change prices, stock or orders are each rejected, logged and audited; prices, flags, stock, orders, seats and settings are compared before and after the run and are unchanged.
  - AC2: an instruction planted in an item description reaches the model only as a value inside a JSON tool result. When the model obeys it, the call is rejected and its malformed proposal dropped; a valid proposal made in the same situation is only stored as PENDING.
  - AC3: the agent's role is denied ten kinds of write.
  - The tests reuse the agent-run fixtures; one lint rule is disabled for that file because it misreads imported fixtures.
- **How it was checked:** 17 tests, rerun after a teammate's output-validation PR (CAFIITK-167) merged; the full suite. Whether a scripted model is a fair stand-in for a real injection was left to the reviewer (see also E50). The PR was approved by a teammate (Suryansh) with no change requests, then merged.
- **Outcome:** accepted.

### Kitchen and Administrator dashboards (CAFIITK-179)

- **Asked for:** the Kitchen screen (queue and transition buttons) and the Administrator screen (items, inventory, service window, agent runs and reports, proposal decisions). The author asked for everything not depending on CAFIITK-159 first, then the buttons once it merged.
- **AI produced:**
  - #50: the Kitchen queue, refreshed every P-POLL and kept on screen when a refresh fails. Administrator tabs for proposals (approve, or reject with a reason, and the reason when nothing was applied), agent runs (start a run, follow it to the end, read its report), items (today's portions, the unavailable flag, adding an item) and the service window. Shared widgets went in a new file, so the Student files were untouched.
  - #55: buttons for the moves each order's state allows; the queue refreshes after a move, and a refused move says why. The backend fix for E66.
- **How it was checked:**
  - Widget tests against a fake server: 23 in #50, 5 more in #55, plus a backend test. Client coverage 97% without the generated code; the web build passes.
  - E70 was caught by these tests before either PR.
  - The AI checked that the backend accepts the date format the generated client puts in URL paths (related to E41).
  - Not tried by hand (E71).
  - Both PRs were approved by a teammate (Suryansh) with no change requests, then merged.
- **Outcome:** accepted.
