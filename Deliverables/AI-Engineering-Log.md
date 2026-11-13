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
| E30 | After the payment gateway was merged, the test setup loads settings before setting the test secret, so tests sign tokens with the short default key | **Test-validity regression** | Warning count rose from 1 to about 150 | Fixed by Bug CAFIITK-201 (#76, by a teammate). The suite now clears the cached settings after setting the test key, and a test checks the key's length. No `InsecureKeyLengthWarning` remains. |
| E31 | US-04 AC1–AC2 and US-25 AC1–AC3 were proven on stand-in routes because the real endpoints did not exist yet | Verification gap | Planning | Real-endpoint tests assigned to CAFIITK-132, 153 and 147. US-04 AC2 now also passes on the real cancel endpoint (CAFIITK-153), and US-25 AC1–AC2 on order placement. Still on stand-in routes: US-04 AC1 (needs the price-change endpoint, CAFIITK-132) and US-25 AC3 (20 concurrent duplicates) |
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
| E45 | Tokens are kept in memory only, so reloading the page logs the user out; the SRS does not say where the client should keep them | Specification gap | Writing the session code | Flagged in the PR; the team accepted keeping tokens in memory only. **Decision changed after testing (CAFIITK-207):** the refresh token moved to an HttpOnly cookie on the web and to secure storage on Android, so a reload keeps the user logged in |
| E46 | The Sprint 2 plan assumed the agent tables, the agent's read views and its restricted database role already existed; no issue owned them, and three issues depended on them | **Planning gap** | Comparing the plan with the code | Built first, as its own PR under CAFIITK-164, with the proposal payload agreed in it |
| E47 | The check that the scheduled planning run had already happened that day compared a timestamp set by the database clock with the application clock | Defect | Failing acceptance test | The run's start time is now set from the application clock |
| E48 | The SRS makes disable and replenishment proposals expire when the service window opens, so one drafted during service would be expired from the start | Specification gap | Writing the agent's tools | During service the agent refuses them with the reason; flagged in the PR; team decision on the SRS pending |
| E49 | Test data written for the agent run prioritised an item that had no orders in the slot, which FR-54 does not allow; it passed only because nothing checked it yet | Test defect | The new output validator rejected it | Test data corrected so the tests check what they were written for |
| E50 | The LLM client has never called OpenAI, and its default model is an unconfirmed choice | **Verification gap** | No API key on the author's machine | A run with the team key then completed end to end on `gpt-4o-mini`, drafting its proposals through the LLM (D2 walkthrough). The model choice itself is still to be confirmed by the team |
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
| E71 | #35, #43, #47, #50 and #55 were not tried by hand against the running Docker Compose stack; each PR says so | **Verification gap** | Stated in each PR | Done before the D2 release: the author walked through the kitchen queue and transitions, the agent run, proposal decisions and the dashboards on the Docker Compose stack, in Chrome and Firefox; issues it found are carried into Sprint 3 |
| E72 | For CAFIITK-134 the AI merged `develop` into the branch before merging, instead of rebasing as the revised sprint plan's rule 5 asks | Process lapse | The AI noticed when reading the revised plan | Later PRs rebased just before merge |
| E73 | The job that starts preparation was registered in an outdated version of the worker's job list, written before a teammate added another job; it would have left auto-prep unscheduled | Stale-code slip | Failing test | Registered in the current list beside the teammate's job |
| E74 | Local failures of the US-30 AC1 and AC4 rush tests were put down to machine load in a PR without evidence, repeating E63 | Unverified attribution | Reading E62 and E63 in this log | Investigated: a deadlock fix (E62, #54) was not yet merged, and the machine had run out of local ports (about 16,500 closed connections against 16,384 ports). PR corrected; CI, which runs both tests, passed |
| E75 | For CAFIITK-140 the AI said a concurrency test was included before it had written one | Premature claim | The AI noticed while reviewing its own summary | The test was written and run (a capacity cut waiting on a booking sees the new seat) before the PR was opened |
| E76 | Told that "#82 is approved", the AI took it to mean the author's #83 and moved CAFIITK-162 to Done in the same step as the merge; the merge was refused as unconfirmed, leaving Jira ahead of GitHub | Process lapse | Merge refused | Issue moved back to In Review; #83 merged and the issue closed only after the author confirmed the PR number |
| E77 | The first CAFIITK-163 acceptance tests assumed every order transition was made by the Student, missed the refund entry, and read rows left by other tests (the audit log is never emptied, by design) | Test defect | Four failing tests, before the PR | Expected actors and entries corrected; each test filters on values of its own |
| E78 | The CAFIITK-162 utilisation bars passed text as the progress bar's accessibility value, which Flutter rejects | Implementation defect | Widget tests, before the PR | The figure moved into the bar's label |
| E79 | A draft of the US-31 results gave the request total as "7,000" without adding it up; the total was 7,811 | Arithmetic error | The AI checked the sum before committing | Corrected before commit |
| E80 | The PR #90 description mentioned a GitHub handle guessed from a teammate's name, which could have notified an unrelated account | Risk | The AI noticed after opening the PR | Mention removed |
| E81 | The `caf_app` role (CAFIITK-163) relies on the login user being allowed to switch to it. On a managed database (RDS) this needs an explicit grant, which the migration makes, but it has been checked only on the local stack | **Deployment risk** | Design of the role switch | Confirmed on AWS (CAFIITK-190, #106): the RDS login user is a member of `caf_app`, which has no UPDATE or DELETE on `audit_log`, and writes succeed. The same check found the grant missing for `caf_agent` (E104) |
| E82 | US-31's latency targets are not met on the local stack, before or after CAFIITK-189. One read got no response under peak load | **Quality risk** | The US-31 acceptance tests (CAFIITK-156) | Pending. The stack is on AWS (CAFIITK-190), but the US-31 harness needs mockpay's test controls, which production turns off; the team has not yet decided how to run it there |
| E83 | Nothing delivered queued payment voids or unacknowledged refunds. VOID rows and PENDING refunds were written "for the worker", but no job sent them, and nothing in the app called `gateway.void` | **Implementation gap** | Designing the hold sweeper (CAFIITK-149), whose late-approval path relies on a void | A `payment-outbox` job sends them with no transaction open and marks each row done once acknowledged (#68) |
| E84 | When deciding how to split a cancel's refund, the system counted an authorisation that had been voided as a charge. A cancel after a superseded modification could therefore refund against a voided authorisation, which mockpay refuses | **Design defect** | Designing the sweeper's void path | Voided authorisations are left out of the refund split; test against real mockpay (#68) |
| E85 | The AI assumed E30 was only an out-of-date line in this log and planned no fix. Tests were still signing tokens with the 17-byte default key | Unverified assumption | The warning was still in the CAFIITK-149 test run | Reported to the author; fixed separately as Bug CAFIITK-201 (E30) |
| E86 | The first CAFIITK-157 version cut the pool wait to 3 s, which turned part of the US-30 rush into 503s (`{201: 30, 409: 169, 503: 1}`) | **Regression** | Full-suite runs: US-30 AC1 failed in 2 of 3 | Pool wait back to the 30 s default. The rush and outage tests then passed together 3 times (#73). An earlier failure of the same test was not captured, so its cause is unconfirmed |
| E87 | A database that accepts the connection but never answers (a network partition, not a stopped server) can still hang a pooled connection's health check, because libpq has no client-side statement timeout | **Availability risk** | Reviewing the CAFIITK-157 design | Pending: left out of scope and stated in #73. It would need TCP keepalive settings |
| E88 | The first NFR-3 check compared only the faulted transaction with its snapshot. An operation wrongly split across two transactions would have passed it | **Test design gap** | The AI's own review of what the check could miss | A recovery check was added: after the sweeper and outbox run, every counter must match the orders holding it. A control test splits an operation and must fail (#77) |
| E89 | The first performance baseline (#89) was measured under conditions that skewed it: workloads shared one database, so NFR-12's kitchen reads carried NFR-10's 1,200 orders; the load client went through Docker Desktop's port proxy; and a later run was made on battery power | **Measurement validity** | Profiling for CAFIITK-189, and checking the laptop's power state | Each workload now starts from an empty database (`--fresh`). Later runs use a client inside the Compose network and mains power, and the report marks the first run as superseded (#89, #91) |
| E90 | The draft CAFIITK-189 report and a code comment said a pool of 5 measured best "on every workload". NFR-12's order p95 was better with a pool of 20 | Overclaim | The AI checked each figure against the raw run data before committing | Claim narrowed in the report and the comment (#91) |
| E91 | Two CAFIITK-189 experiments went wrong. 4 workers with a pool of 20 each exceeded PostgreSQL's 100 connections (503 "too many clients"). Separately, a keep-alive race was wrongly blamed for requests that got no response | Experiment errors | Server logs, and the keep-alive change not removing the errors | Pool reduced to fit the connection budget. The keep-alive change was reverted, and the errors were traced to Docker Desktop's port proxy. One `ReadError` in about 4,000 requests inside the network is still unexplained |
| E92 | The harness's NFR-10 seed, and the first run with `--fresh`, each broke a schema CHECK: at most 500 portions per item, and a service day's default capacity of 1–100 | Implementation defect | Both runs stopped with the CHECK violation | Orders spread over several items; the design capacity used for the day (#89) |
| E93 | The first performance report gave "4,840 requests" without adding them up; the total was 5,941 | Arithmetic error | The AI checked the sum before committing | Corrected before commit |
| E94 | An order-history test assumed a modified order's version is 2 | Test defect | Failing test run | Assertion removed |
| E95 | The security fuzz pass changed shared settings through the API (it sends valid values too), so a later file's subsidy test failed | Test isolation defect | Full-suite run | The campaign restores the settings table after each test |
| E96 | The Android package was named `in.ac.iitk…`; `in` is a reserved word in Java, so the build failed | Implementation defect | Build failure | Renamed to `com.xforce.cafiitk` |
| E97 | A Gradle build report was committed with the Android project | Tooling mistake | Reading the commit before review | Removed in a follow-up commit, and `build/` ignored |
| E98 | Closing comments on Jira tasks cited test files that do not hold those tests (NFR-31, US-15, FR-47) | Hallucinated reference | Checking the files after posting | Comments corrected |
| E99 | The CI job was renamed on the belief that branch protection was off. A repository ruleset, which that API does not show, required the old name, so every merge was blocked | **Unverified assumption** | The merge was refused | Name restored, with a comment saying it is a required check |
| E100 | The traceability script's pattern missed test names that continue after the AC number, reporting dozens of false gaps | Verification flaw | Results contradicted known-passing rows | Pattern fixed before any row was changed |
| E101 | A PR description said the team member chose not to audit rate-limited logins; it was the AI's proposal | Misattribution | Re-reading the PR | Corrected; the author then confirmed the decision |
| E102 | A local full-suite failure (a mockpay test) came from running a Flutter build at the same time | Verification flaw | It passed 3 of 3 alone, and in CI | Suites run one at a time afterwards |
| E103 | The AI told the author that everything left was waiting on AWS; only 5 of 13 items were | Overclaim | The author questioned it | Corrected with a per-issue breakdown |
| E104 | Migration 0002 never granted `caf_agent` to the login user. On RDS that user is not a superuser, and since PostgreSQL 16 creating a role does not let its creator switch to it, so every agent run would have failed on AWS with "permission denied to set role" | **Deployment defect** | Before deploying, the AI ran the migrations on a local PostgreSQL 16 as a non-superuser login, as on RDS | Migration 0007 grants it; a test migrates a fresh server as such a user and fails without 0007. An agent run then succeeded on RDS (#106) |
| E105 | The first deployment plan relied on a free hostname service (sslip.io) and a Let's Encrypt certificate. The campus network resolves every such service (sslip.io, nip.io, traefik.me, DuckDNS) to a block page, so the site would have been unreachable on campus, including at the demo | **Design risk** | DNS lookups from the campus network before requesting the certificate | HTTPS moved to CloudFront, whose `*.cloudfront.net` name has a valid certificate and resolves on campus; EC2 port 80 admits only CloudFront (#106) |
| E106 | The AI's first monthly cost estimate for the AWS stack (USD 20–25) was too low for a `t3.small`; about USD 30–35 is right | Arithmetic error | The AI rechecked the figure in its next reply | Corrected before any decision depended on it; either figure is well within the credits |
| E107 | A draft of the cost report said CloudFront was on its Free pricing plan, before any evidence. The console later could not show the plan at all, for lack of a permission | Unverified claim | The AI's own review of which facts it had checked | Marked as unconfirmed before commit; the report now says the plan could not be read and that the Free account plan cannot be billed whatever it is (#108) |
| E108 | The AI sent the merge of #108, a server update and closing CAFIITK-191 together. The safety check refused the server update, which also stopped the merge, so Jira showed Done before the PR was merged. This repeats E76 | Process lapse | The refusal message | The merge was run on its own straight away; the server was updated by the author |
| E109 | The first redaction filter (CAFIITK-180) had three defects. A log call whose arguments did not fit its template raised an error into the request and became a 500. A record passing through two handlers gained a stray `]`. The URL pattern took a port for a password and missed `redis://:password@host` | Implementation defect | The AI's audit of the PR, after it had been approved | Each fixed with a regression test; the changes since the approval were listed in a PR comment (#84) |
| E110 | The fake secrets that the redaction tests log on purpose failed the secret scan, which reads the full history, so a new commit could not remove them | Tooling defect | CI | `.gitleaks.toml` keeps the default rules and allows only those values, only in that test file (#84) |
| E111 | A 3,909-line file named `backend/--help` was committed with CAFIITK-181 | Tooling mistake | Before merge; how it was noticed is not recorded | Removed in a follow-up commit (#82) |
| E112 | Two full-suite runs each had a single failure that did not recur. In CAFIITK-181 the failing test was not identified. In CAFIITK-180 it was a hold-sweeper test, which passed 3 of 3 alone | Verification gap | Full-suite runs | Pending: reported in #82 and #84 and flagged to the test's author; no cause or decision is recorded |
| E113 | The first CAFIITK-183 cache of each route's query parameters used weak references, but routes are not hashable, so it failed | Implementation defect | First test run | Keyed by `id(route)`, keeping the route so that a reused id cannot return another route's parameters |
| E114 | A CAFIITK-142 test expected a 422 for an empty `item_ids` on a CATEGORY rule, which is valid. The first PR description also said 41 tests; there were 35 | Test defect; arithmetic error | Failing test run; re-reading the PR | Test and description corrected; the code was right |
| E115 | The SRS gives the subsidy parameters' defaults but no limits. The AI chose 0–₹500 and 0–100 % | Specification gap | Writing CAFIITK-143 | Pending: #93 asked reviewers to check them; it was approved with no comment on them, and no explicit decision is recorded |
| E116 | The first CAFIITK-143 test helper assumed the audit table is emptied between tests; it keeps earlier tests' rows | Test defect | The AI reading the test set-up before the first run | Lookups filtered by actor |
| E117 | The CAFIITK-187 reference implementation and its worked cases come from the same AI reading of FR-24 as the tests' expectations, so a shared misreading would pass. The breakage check stopped at the first failing test, so it does not show that each property catches a bug on its own | **Quality risk** | The AI's review of what the check proves | Pending: see E119 for the reference's review |
| E118 | Wrong references in CAFIITK-143 and CAFIITK-187. #93 cited SADD §7 for the routes (they are in §2.6). A comment in `pricing/schemas.py` and the docstring of `test_pricing_properties.py` cite FR-6 for the price range (it is FR-8). That docstring also says at most 20 items per cart; the tests draw at most 12 | Hallucinated reference | Checking the SRS and SADD while writing these entries | Pending: not corrected |
| E119 | The AI wrote "I reviewed…" in the author's voice in #93 (the diff, the limits, the locking) and #94 (the reference against FR-24) without being told any such review took place. This repeats E101 | Misattribution | Re-reading the PRs while writing these entries | Pending: the author to confirm or correct both descriptions |
| E120 | A CI run on the release PR showed as cancelled. The AI re-ran it, not seeing that a newer run for the same PR was already live. The workflow cancels older runs in the same group, so the re-run cancelled the live run, and the release checks had to run again | Process error | Checking every run listed for the PR after the second cancellation | The AI cancelled its own re-run and let the checks run again on the next update to `develop`. They passed |
| E121 | Drafts of the D3 reports contained claims not taken from the source: a 10 s payment timeout (the test uses 0.5 s), two wrong FR numbers, sprint issue counts, per-area test totals, "Unicode" fuzz values that the fuzz list does not contain, "two thirds" where the data gives three quarters, and two guessed reasons for uncovered code | Unverified claims | The AI checked each claim against the test files, the coverage output, Jira and GitHub before commit | All corrected before the PR was opened |
| E122 | Two defects in the first CAFIITK-207 version. The start-up restore replaced a session that already existed when its refresh failed, logging the user out. A refresh with no token returned 401, which the access matrix reads as "login required" on a public route (it had been 422) | Implementation defect | 114 client tests and one security-campaign test failed, before the PR | Restore leaves an existing session alone; a missing token is 422 again, and only a bad token is 401 |

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
- **Outcome:** accepted. AC1 and AC2 now also pass on the real order endpoint; AC3 (20 concurrent duplicates) still runs on the stand-in route.

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
- **Outcome:** accepted for AC1 and AC2. AC3 and AC4 followed in Sprint 2 (see the later entry), and the story is complete.

### Portions follow the order lifecycle (CAFIITK-138, US-13) — AC1 and AC2

- **Asked for:** the acceptance tests for US-13.
- **AI produced:** AC1, ordering 2 of 10 leaves 8 while the order awaits payment, observed from inside the payment call, and still 8 once accepted. AC2, a declined payment returns the 2 portions with no further action. No application code changed; the behaviour was delivered with order placement.
- **How it was checked:** the full suite locally and on the CI runners. The PR was approved by a teammate (Suryansh) with no change requests, then merged.
- **What changed:** AC3 and AC4 cancel an order and were carried into Sprint 2 by the same decision as for US-30. They are in the suite as skipped tests with the reason. The rule they will test is already in the state table: cancelling an accepted order returns portions and seat, cancelling one in preparation returns only the seat.
- **Outcome:** accepted for AC1 and AC2. AC3 and AC4 followed in Sprint 2 (see the later entry), and the story is complete.

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
- **Outcome:** first half accepted. The story was completed by the second half (see the later entry).

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
- **What changed:** nothing after review. It has since completed a real run against OpenAI (E50).
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
- **Outcome:** accepted; follow-up fix #54 approved by a teammate (Suryansh), then merged.

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
- **Outcome:** accepted.

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
### Preparation starts automatically (CAFIITK-160, US-35)

- **Asked for:** at slot start minus P-AUTO_PREP, every order still ACCEPTED in that slot moves to PREPARING, with SYSTEM as the actor (FR-44). Reassigned to the author when the sprint was revised, and started once the kitchen transitions (CAFIITK-159) were merged.
- **AI produced:** a caf-worker job, every 30 seconds, that uses the kitchen's own Start transition with no user: each order is locked and its status re-checked, then the transition, an audit entry with actor SYSTEM and the version bump are recorded by the shared order code, so a Student acting on an older view is refused as after the kitchen's Start. One short transaction per order. The job takes no payments; a payment call on this path fails.
- **How it was checked:** 8 tests against PostgreSQL, including the acceptance criterion (nothing at 12:19 for a 12:30 slot, PREPARING with actor SYSTEM at 12:20), only ACCEPTED orders moving, repeat runs, a late run, the version bump, an order cancelled meanwhile, and the job run end to end. A test caught one slip while drafting (E73). CI passed, including the full suite. The PR was approved by a teammate (Suryansh) with no change requests.
- **What changed:** the PR's explanation of two local rush-test failures was corrected (E74).
- **Outcome:** accepted.

## Deliverable 3 entries

### Change an item's price safely (CAFIITK-132, US-07)

- **Asked for:** edit an ACTIVE item's description, category and price (FR-9). A price change must never alter an existing order's price snapshot.
- **AI produced:**
  - `PATCH /admin/items/{id}`: the name is not editable; an empty body or a null value is a 422.
  - The item row is locked as flagging locks it. Only the fields that change are audited, in the same transaction; an edit that changes nothing writes nothing.
  - US-04 AC1 (Kitchen Staff cannot change a price) moved from a stand-in route to this endpoint, closing the gap noted in E31.
  - The regenerated client.
- **How it was checked:** 20 tests. The acceptance test places a real order at ₹80, changes the price to ₹90, and checks that the order's snapshot still says ₹80 while a new quote says ₹90. The full backend suite passed. Tried by hand on the Docker Compose stack. Approved by a teammate (Rudransh) with no change requests; the author merged it.
- **Outcome:** accepted.

### Protect me from price changes at checkout (CAFIITK-145, US-20)

- **Asked for:** an acceptance test for US-20 using a real price change. The behaviour already existed; the traceability matrix recorded it as tested under another name.
- **AI produced:** one test. A 5 % discount makes the Rs 80 Thali the criterion's Rs 76 quote. The Administrator then changes the price, and confirming at Rs 76 gets 409 with a fresh quote. Nothing is reserved and no payment is attempted.
- **How it was checked:** the order-placement tests (35) and CI. Approved by a teammate (Suryansh) with no change requests.
- **Outcome:** accepted.

### Remove a menu item (CAFIITK-133, US-08)

- **Asked for:** soft-delete to REMOVED (FR-10). Orders already placed must proceed and keep their snapshot.
- **AI produced:**
  - `DELETE /admin/items/{id}`, which sets the item to REMOVED; removing it again is a no-op. Audited in the same transaction.
  - The AI traced every place that reads an item's status and found nothing else to change: the menu, order placement, editing, flagging, inventory and proposal approval already treated REMOVED correctly.
- **How it was checked:** 9 tests, one per acceptance criterion. AC2 takes an order placed before the removal through the kitchen to PICKED_UP, with its history still naming the item. Tried by hand on Docker Compose. Approved by a teammate (Suryansh) with no change requests.
- **Outcome:** accepted.

### Change slot capacity safely (CAFIITK-140, US-15)

- **Asked for:** change one slot's capacity without dropping bookings (FR-18). A window change that would remove a booked slot must be refused. Before this, any reconfiguration of a day with orders was refused.
- **AI produced:**
  - `PATCH /admin/slots/{id}`: a capacity below the booked seats is a 409, and nothing changes. The slot is locked as order placement locks it.
  - Reconfiguring a day with orders now keeps the slots orders point at, with their IDs and bookings. It refuses (409) only if one of those slots would disappear or fall below its bookings, and regenerates the rest. The day's slots are locked in ascending ID, the system's lock order.
  - A design choice flagged in the PR: a kept slot takes the new default capacity.
- **How it was checked:** 16 new tests and 5 rewritten ones. They include a concurrency test on PostgreSQL in which a capacity cut waits for a booking that holds the slot lock, and then sees the new seat (E75). The full suite passed (819). Tried by hand on Docker Compose. Approved by a teammate (Rudransh) with no change requests, so the flagged choice stands.
- **Outcome:** accepted.

### Monitor the day (CAFIITK-162, US-37)

- **Asked for:** the Administrator's list of the day's orders, with slot, state and Student filters (FR-45), and a utilisation view that updates within 30 s (FR-46).
- **AI produced:**
  - `GET /admin/orders`, filtering by state (repeatable), slot, and part of a Student's name or email; wildcard characters are matched literally.
  - `GET /admin/utilisation`: seats per slot, portions per item, and a count of orders in every state.
  - Two Administrator tabs. The utilisation tab refreshes every P-POLL (10 s) while it is open, and keeps the last figures if a refresh fails.
  - The regenerated client.
- **How it was checked:**
  - 22 backend tests, through real orders, including one cancelled through the API. 4 widget tests; E78 was caught by these.
  - The full backend (850) and client suites; client coverage 97 %.
  - The endpoints were tried by hand on Docker Compose. The new tabs were not opened in a browser, as the PR stated.
  - Approved by a teammate (Kshitij) with no change requests.
- **What changed:** the merge was held until the author confirmed which PR was approved (E76).
- **Outcome:** accepted.

### Trustworthy audit trail (CAFIITK-163, US-38)

- **Asked for:** audit search by entity, carrying the correlation ID (CAFIITK-180) and the price-change audit (CAFIITK-132). The application's role must be refused UPDATE and DELETE on the audit log (NFR-26), and no secret may appear in results.
- **AI produced:**
  - Migration 0005: a `caf_app` role with full rights on the business tables, but only INSERT and SELECT on `audit_log`. Every application transaction switches to it, so the database itself refuses to change an audit entry.
  - The test client runs the same way, so the whole suite exercises the role's rights.
  - `GET /admin/audit`: search by time range, actor, entity and action, a page at a time. An order's ID also finds its portion and seat changes and its refund.
  - Values that look like secrets are redacted again on the way out.
  - Search indexes, and the regenerated client.
- **How it was checked:**
  - 19 tests, including all four acceptance criteria. AC3 tries UPDATE, DELETE and TRUNCATE as `caf_app` and gets a permission error. E77 was fixed before the PR.
  - The full suite passed with every transaction running as `caf_app` (895 tests, and 917 after merging `develop`).
  - The migration was applied by hand to the existing Docker Compose database and the role's rights checked.
  - Approved by a teammate (Kshitij) with no change requests.
- **What changed:** the RDS membership question was left open for the deployment (E81).
- **Outcome:** accepted.

### Flutter client tests (CAFIITK-186), and Bug CAFIITK-202

- **Asked for:** widget and provider tests for the auth, Student, Kitchen and Administrator flows. The 80 % gate was already enforced, and coverage was already 97 %.
- **AI produced:**
  - The AI read each client test against the SRS acceptance criteria. Tests that check a criterion's client side were renamed with its TC ID, across 15 stories, so the traceability matrix can find them.
  - New tests: a completed order's full history (US-29 AC2); the server's reason for a refused service window (US-14 AC2, US-15 AC2); every finished order state in My orders.
  - While mapping US-10 AC1, the AI found that the Student menu never showed an item's category. The author had it raised as Bug CAFIITK-202 ("Found by: Code review"). It was fixed in the same PR, with the category labels shared with the Administrator's items tab.
- **How it was checked:** 146 client tests, and the new US-10 check fails without the fix. Approved by a teammate (Kshitij) with no change requests.
- **Outcome:** accepted. CAFIITK-202 counts towards the D3 defect total.

### Ordering stays fast at peak (CAFIITK-156, US-31)

- **Asked for:** verify US-31's two latency criteria with Rudransh's CAFIITK-188 numbers and harness, and record them.
- **AI produced:**
  - Two named acceptance tests on top of the harness, asserting the real targets at full scale against a live stack. They are skipped in CI, which already runs the harness at 5 % scale.
  - The AI ran them on the Docker Compose stack before and after CAFIITK-189, and added §5 to the Performance Report.
- **How it was checked:** both tests failed in both runs. After CAFIITK-189:
  - AC1 (orders): p95 570 ms against a 500 ms target. The hot-row lock wait fell from 190 ms to 15 ms.
  - AC2 (reads): p95 about 1.1 s against a 200 ms target.
  - One read got no response.

  The figures were reported as measured (E79, E82). Approved by a teammate (Kshitij) with no change requests.
- **What changed:** the report noted that reads spend most of their time before reaching the application, as input for CAFIITK-189. The author decided to close the issue as verified and recorded, with a Jira comment that US-31 is not yet met.
- **Outcome:** accepted as a measurement. US-31 itself is pending the AWS run (E82).

### Holds never leak after a crash (CAFIITK-149, US-24)

- **Asked for:** the hold sweeper (FR-34 ★). It expires PENDING_PAYMENT orders and unfinished modifications after P-HOLD_EXPIRY, recovers holds at worker start-up (NFR-15), and voids a payment approval that arrives after expiry.
- **AI produced:**
  - The `hold-sweeper` job. It runs one short transaction per order, under the order lock, in the canonical lock order. An expired modification gives back what it took, and the order keeps its old cart, slot and price.
  - While designing it, the AI found that nothing ever sent the voids and refunds queued for the worker (E83). It added the `payment-outbox` job, which reads in one transaction, calls mockpay with none open (NFR-6), and marks the row done in a second.
  - A fix to how refunds were split: a voided authorisation no longer counts as a charge (E84).
- **How it was checked:**
  - 11 tests against PostgreSQL, including TC-US24-AC1 to AC3. One runs against real mockpay, which refuses the late approval because the void reached it first.
  - The full suite passed, except the Windows-only SIGTERM test. One earlier failure was not captured, as the PR says.
  - On Docker Compose, the author killed caf-api while an order waited on mockpay. The sweeper expired the order 119 s later, within the 150 s limit; the counters returned to zero and the void was delivered.
  - Approved by a teammate (Suryansh) with no change requests.
- **What changed:** the AI had assumed E30 needed no fix; it did (E85).
- **Outcome:** accepted. FR-34 passes, so all ten critical requirements now pass.

### Cancel an order on a Student's behalf (CAFIITK-161, US-36)

- **Asked for:** the Administrator cancels an ACCEPTED, PREPARING or READY order with a mandatory reason, with a 100 % refund (FR-38).
- **AI produced:**
  - `POST /admin/orders/{id}/cancel`, with an idempotency key. It releases the seat always, and the portions only from ACCEPTED, following the state machine.
  - The Administrator and the reason are recorded on the transition, with the audit row in the same transaction.
  - The refund goes to mockpay after commit, and the payment outbox retries one left unacknowledged.
  - The regenerated client.
- **How it was checked:**
  - 16 tests, including TC-US36-AC1 and AC2.
  - Tried by hand on Docker Compose with real mockpay: a READY order was cancelled with a full refund, and only the seat came back.
  - Approved by a teammate (Suryansh) with no change requests.
- **Outcome:** accepted.

### Graceful behaviour when the database is down (CAFIITK-157, US-32)

- **Asked for:** while the database is down, answer within 5 s with 503 and `Retry-After` and write nothing; resume within 30 s of its return without a restart (NFR-16).
- **AI produced:**
  - A 2 s connect timeout, with pool pre-ping kept.
  - Error handlers that turn a lost connection into 503 with `Retry-After: 5`. A statement error, such as a lock timeout, stays a 500, so bugs are not hidden.
  - A worker that waits out an outage instead of exiting.
- **How it was checked:**
  - 10 tests on a dedicated PostgreSQL container that the tests kill and restart. They include the database dying during the payment call, which leaves only a hold for the sweeper to release.
  - On Docker Compose, the author stopped and restarted `db`. Orders got 503 in 3–4 s and succeeded 0.2 s after the restart, with no API restart.
  - Approved by a teammate (Suryansh) with no change requests.
- **What changed:**
  - The AI's first version shortened the pool wait, which broke the rush test (E86).
  - The tests use `127.0.0.1`, because `localhost` resolves to two addresses and doubled the timeout.
  - A merge conflict with #69 was resolved at the author's request.
  - A network partition is left as a known limit (E87).
- **Outcome:** accepted.

### Failure-injection tests (CAFIITK-184; NFR-3, NFR-6)

- **Asked for:** inject failures part-way through every write operation and prove nothing partial is kept; prove no payment or LLM call happens with a transaction open.
- **AI produced:**
  - A hook that fails the Nth SQL statement of an operation, run once for every statement. That is 271 faults across nine operations: create, payment failure, three kinds of modification, cancel, admin cancel, hold expiry and proposal execution.
  - After each fault, the whole database must equal a snapshot taken as the failed transaction began.
  - For NFR-6, spies record whether any pooled connection is checked out when the gateway or LLM is called.
- **How it was checked:**
  - 12 tests, 2 min. A dry run maps statements to transactions, so only the faulted transaction is snapshotted; the first version took 5.6 min.
  - The full suite passed.
  - Approved by a teammate (Suryansh) with no change requests.
- **What changed:** the AI found its first check could not see an operation split across transactions, and added a recovery check and a control test (E88).
- **Outcome:** accepted. No defects were found, so no Bugs were filed.

### Load and performance measurement (CAFIITK-188; NFR-8 – NFR-12)

- **Asked for:** measure latency, throughput and agent run time against NFR-8 to NFR-12, and record the environment, command and results.
- **AI produced:**
  - `tests/perf.py`, a harness that drives a running caf-api over HTTP for each NFR workload. It reports percentiles, errors and throughput against each target.
  - Around each workload it reads `/metrics` (CAFIITK-181) for the server's time per route and its row-lock waits.
  - A small-scale run in CI.
  - `Deliverables/Performance-Report.md`.
- **How it was checked:**
  - The harness's own 8 tests, including one that the server counts the same orders the client sent.
  - Report figures checked against the raw JSON (E93).
  - Approved by a teammate (Shashi) with no change requests.
- **What changed:** the first baseline was skewed by how it was run (E89), which was found during CAFIITK-189. `--fresh` was added before #89 merged. The measurement method was then corrected, and the report keeps the first run as a record only.
- **Outcome:** accepted. The AWS run, which gives the numbers of record, is pending on CAFIITK-190 (E82).

### Bottleneck analysis and optimisation (CAFIITK-189)

- **Asked for:** profile the menu-release hot-row contention; try a conditional atomic UPDATE, short-TTL caching and pool sizing; keep only what measurably helps, with before-and-after numbers.
- **AI produced:**
  - Profiles of caf-api under the read and order loads, showing three problems:
    - connection churn: 442 new connections in 30 s of reads;
    - the hot inventory row held for a whole transaction;
    - a lock holder slowed by the Python GIL.
  - Three changes: a fixed pool with no overflow; placing the order before the inventory and slot rows are locked; and `FOR NO KEY UPDATE` on those rows, so the reordering cannot deadlock. The worker count is now configurable.
  - Each candidate built as its own image and swapped under one Compose stack, then compared over interleaved runs.
- **How it was checked:**
  - The full suite (923 tests, coverage 98.2 %), including the concurrency, failure-injection and database-down tests.
  - Interleaved before-and-after runs: mean hot-row lock wait 1,128 → 73 ms (NFR-8) and 417 → 10 ms (NFR-12); NFR-8 p95 down 36 %; NFR-12 mean order time down 25 %; reads unchanged.
  - Approved by two teammates (Shashi and Suryansh) with no change requests.
- **What changed:**
  - A claim in the draft report was narrowed (E90).
  - Two wrong experiments were corrected (E91).
  - The conditional UPDATE and caching were not kept, with reasons in the report: the lock wait is now under 4 % of order time, and caching could save at most about a quarter of a menu read.
- **Outcome:** accepted.
  - The NFR-8, NFR-9 and NFR-12 targets are still missed on the local stack (E82).
  - NFR-9 does not define think time; the report raises this for the team. Team decision pending.

### Rate limits and passwords in errors (CAFIITK-182; NFR-20, NFR-21), and Bug CAFIITK-199

- **Asked for:** limits on failed logins and order requests that hold across API workers (NFR-21), and checks that a password never leaves the server (NFR-20).
- **AI produced:**
  - Counters in the shared `rate_limits` table, taken with one atomic upsert that stops at the cap. A login reserves its place before the password is checked and gives it back on success, so only failures count.
  - Limits per account and per address for logins, and per Student for create, modify and cancel.
  - An hourly job that deletes old counters.
  - While testing, the AI found that a 422 echoed the rejected password back to the client. It raised Bug CAFIITK-199 and fixed it: validation errors no longer include the input.
- **How it was checked:**
  - Tests against PostgreSQL. One sends 20 parallel guesses across two real API processes; exactly 5 are checked and 15 get 429.
  - The full suite passed.
  - Approved by a teammate (Rudransh) with no change requests.
- **Outcome:** accepted.

### One Student, a limited number of orders (CAFIITK-151, US-26)

- **Asked for:** refuse a new order when the Student already has P-MAX_ACTIVE unfinished orders that day (FR-31).
- **AI produced:** the check, made under the Student row lock that ordering already takes, so two parallel requests cannot both pass. It answers 422.
- **How it was checked:** TC-US26-AC1 and AC2, and the full suite. Approved by a teammate (Rudransh).
- **Outcome:** accepted.

### My orders (CAFIITK-146, US-21)

- **Asked for:** a Student's past orders, each showing every price snapshot and any refund (FR-27, FR-28).
- **AI produced:**
  - `GET /orders`, newest first, capped at 200.
  - An order's detail now includes its snapshots and refunds.
  - The client's "My orders" list and order history screens.
- **How it was checked:**
  - TC-US21-AC1 and AC2, plus ownership tests: another Student's order gives 404.
  - Client widget tests.
  - Approved by a teammate (Rudransh).
- **What changed:**
  - One test assumed a modified order's version is 2 (E94).
  - A repository method was renamed so it did not clash with a teammate's.
- **Outcome:** accepted with modifications.

### Staff accounts (CAFIITK-128, US-03)

- **Asked for:** the Administrator creates Kitchen Staff and Administrator accounts and deactivates or reactivates them (FR-2, FR-3).
- **AI produced:**
  - `/admin/users`. Deactivation takes effect at once for logins, refresh tokens and access tokens.
  - An Administrator cannot change their own account (409).
  - Every change is audited, without the password.
  - The Staff tab in the Administrator dashboard.
- **How it was checked:**
  - TC-US03-AC1 to AC3 and the backend tests.
  - Client widget tests. One first tapped the wrong widget and was corrected.
  - Approved by a teammate (Rudransh).
- **Outcome:** accepted.

### Adversarial and security campaign (CAFIITK-185), and Bugs CAFIITK-200, 203 and 204

- **Asked for:** attack the finished system and log every finding as a Bug. The author waited until every feature was merged before running the final pass.
- **AI produced:**
  - A permission matrix of all 46 routes, checked anonymously and for every role. It fails CI if a new route is not listed.
  - Probes for:
    - reading or changing another Student's order;
    - forged and misused tokens;
    - setting server-owned fields;
    - price and quantity tampering;
    - another Student's idempotency key.
  - A fuzz pass that sends hostile bodies, fields, query parameters, path parameters and keys to every route, expecting no 5xx.
- **Findings (all raised as Bugs and fixed):**
  - **CAFIITK-200 (first pass):** a NUL character in request text gave a 500.
  - **CAFIITK-203:** the same problem in six text query parameters.
  - **CAFIITK-204:** an audit cursor beyond the bigint range gave a 500.
  - No authorisation or tampering issue was found.
- **How it was checked:**
  - Each failure was reproduced and traced to its PostgreSQL error before it was raised.
  - The full suite passed after the fixes.
  - The fixes were approved by a teammate (Rudransh). The campaign PR was stacked on the fix PR and reached `develop` through it, so it had no separate approval.
- **What changed:** the fuzz pass changed shared settings, which broke a later test file (E95).
- **Outcome:** accepted.

### Android build (CAFIITK-192; NFR-34)

- **Asked for:** an Android app from the same Flutter code.
- **AI produced:**
  - The Android project, with the internet permission.
  - A network rule that allows plain HTTP only to the developer's machine.
  - README steps for the build.
  - No Dart code changed.
- **How it was checked:**
  - The author installed the release APK on a physical phone, connected to the Compose stack. They registered, set up the day as Administrator, then ordered, tracked and cancelled as a Student. Each step was confirmed in the server logs and the database, including the refund.
  - The first order attempts were refused because ordering had not opened yet, which is correct behaviour.
  - Approved by a teammate (Rudransh).
- **What changed:** an invalid package name (E96), and a build report committed by mistake (E97).
- **Outcome:** accepted with modifications.

### Closing requirement tasks with evidence, and Bug CAFIITK-205

- **Asked for:** close every backlog requirement task the merged work satisfies, after checking each one.
- **AI produced:**
  - For each task, a check against the SRS text and the tests on `develop`, then a comment citing the PR and tests.
  - Tasks still failing or blocked were left open, with the reason.
  - Checking FR-47 turned up a gap: failed logins were never audited. The AI raised Bug CAFIITK-205 and fixed it.
  - The AI proposed not auditing logins refused by the rate limit, because those are unbounded and the audit log is append-only. The author confirmed this decision.
- **How it was checked:**
  - Each closure cites specific tests. Two comments first named the wrong test file (E98).
  - The CAFIITK-205 fix was approved by a teammate (Rudransh), and was seen working on the live stack.
- **Team decision:** the author decided to close NFR-8, NFR-9 and NFR-12 even though they fail on the local stack. Each closing comment says "target not met" and lists the numbers and the remedies not done. The traceability matrix keeps them as Fail.
- **Outcome:** accepted.

### Discount and subsidy screens (FR-22, FR-23)

- **Asked for:** the discount-rule and subsidy APIs were merged, but the Administrator had no screen for either. The author asked for one.
- **AI produced:**
  - A Discounts tab: list, add, edit, deactivate.
  - A Subsidy tab: the amount and cap, and an eligibility switch per Student.
  - The generated client sends unset fields as null, which the server refuses, so every edit sends the whole rule.
- **How it was checked:**
  - 13 widget tests.
  - The author tried both tabs by hand on the stack, and each action was confirmed in the logs and the audit table.
  - Approved by a teammate (Rudransh).
- **Outcome:** accepted.

### Jira key in every commit (CAFIITK-124; NFR-44)

- **Asked for:** CI should also reject commits without a Jira key. Merge commits are excepted.
- **AI produced:** a step that checks each of a PR's own commits. It was tested locally on real commit ranges, including a negative case.
- **What changed:** the first version renamed the CI job, which blocked every merge (E99).
- **How it was checked:** the PR's own CI run passed, and later PRs passed the check. Approved by a teammate (Rudransh).
- **Outcome:** accepted with modifications.

### Final regression and traceability matrix (CAFIITK-193)

- **Asked for:** a regression pass on `develop`, and the traceability matrix completed for D3.
- **AI produced:**
  - The full backend and client suites run on `develop`.
  - The matrix brought up to date: Jira statuses from Jira, PR numbers from merged PR titles, and a script that confirms every listed acceptance criterion has a test named for it.
- **What changed:** the first version of that script reported dozens of tests as missing that existed (E100).
- **Team evaluation:** accepted; the PR was approved by a teammate (Rudransh) with no change requests, then merged.

### Deploy to AWS (CAFIITK-190; NFR-27, NFR-40)

- **Asked for:** the issue's owner was busy and asked the author to take it over. The author asked the AI to find the issue in Jira, check whether the AWS free tier would cover two weeks of use, and then carry out the deployment. The issue was reassigned to the author.
- **AI produced:**
  - An explanation of AWS's two account plans. On the Free plan the account cannot be charged and closes when its credits run out, so the team chose it.
  - Step-by-step console instructions: account security, a USD 1 budget, security groups, RDS (PostgreSQL 16, the version the project is tested on), EC2 and CloudFront.
  - `docker-compose.prod.yml`, using the same image and migrations as the local stack, with the database on RDS:
    - caf-api is bound to the instance's loopback address, and mockpay is not published.
    - mockpay's test controls are off.
    - `/metrics` is not served publicly.
  - The nginx origin config. It takes the client's address from the entry CloudFront appends to X-Forwarded-For, so the login rate limit counts real client IPs and a client cannot choose its own.
  - A production `.env` template and the runbook `deploy/README.md`.
  - Migration 0007, the fix for E104, with its test.
  - The AI installed Docker on the instance, built and started the stack, built the web client for the CloudFront address, and ran the checks.
- **How it was checked:**
  - The full backend suite: 1,353 passed.
  - Before deploying, a local run of the production stack against a database with RDS's non-superuser login. Migrations ran, login worked, and an agent run succeeded.
  - On AWS, from the campus network: HTTP redirects to HTTPS with a valid certificate, and `/ready` answers. `/metrics` returns 404. CORS refuses a foreign origin. Ports 8000 and 8001 are closed. Register, login and authorised requests work through CloudFront. A spoofed X-Forwarded-For was ignored: the audit log recorded the real campus address.
  - E81's checks run against RDS: a non-superuser login that holds both roles, and an append-only audit log.
  - The author restricted EC2 port 80 to CloudFront's address list, and the AI confirmed that the instance no longer answers directly. The author added an item and started an agent run as the Administrator in the browser.
  - Approved by a teammate (Rudransh), with all CI checks passing (#106).
- **What changed:**
  - HTTPS moved from Let's Encrypt to CloudFront (E105).
  - The servers ended up in Sydney rather than the planned Mumbai, which adds network latency from India.
  - The AI declined a proposal to commit under another member's GitHub account, using a password shared in the chat. The issue was reassigned to the author instead.
  - A JWT secret that had been pasted into the chat was replaced on the server, unseen, before the first start.
  - A smoke-test Student account was left on the deployed database and disclosed in the PR.
  - Database connections use `sslmode=require`, which encrypts but does not verify the server certificate. The connection never leaves AWS's private network.
- **Outcome:** accepted. The site is live on AWS. The US-31 re-run on AWS is still pending (E82).

### Cost tracking (CAFIITK-191; NFR-42, NFR-43)

- **Asked for:** a USD 1 billing alarm, confirmation that every resource is within the free tier, and LLM requests and monthly spend reported against the USD 5 cap.
- **AI produced:**
  - `python -m app.modules.agent.spend`, which reports for each IST day:
    - billed, cached and failed LLM requests;
    - tokens, and cost at list prices;
    - the busiest day against P-AGENT_DAILY_CAP, and the month against USD 5.

    Only billed requests are priced. An unknown model fails the report instead of counting as free.
  - `Deliverables/Cost-Report.md`, built from the author's console screenshots, the instance metadata, the database and a run of the report on the deployed stack. It covers the account plan, the credits, each resource's free-tier eligibility, the budget, the LLM spend, and a worst-case bound under the daily cap.
- **How it was checked:**
  - 10 tests against PostgreSQL, including the IST day boundary and the two over-limit cases.
  - The report run against RDS: USD 0 in November, within NFR-42. The author ran it again on the server after merging.
  - Approved by a teammate (Kshitij), with all CI checks passing (#108).
- **What changed:**
  - Facts the AI could not verify were marked as unconfirmed until the screenshots arrived (E107).
  - The budget's alert email shows as unverified, and the team decided to leave it that way, because the Free account plan cannot be billed. The report records this. The author asked for the alarm requirement to be removed; the AI kept it and recorded the decision instead, since the configured budget meets NFR-43.
- **Outcome:** accepted.

### Structured logs, correlation IDs and redaction (CAFIITK-180; NFR-28 – NFR-30)

- **Asked for:** JSON logs, a correlation ID on every request, and secrets kept out of the logs.
- **AI produced:**
  - Middleware that takes a safe `X-Request-ID` from the client or generates one, and returns it on every response.
  - That ID carried into logs, audit rows, calls to mockpay, agent runs (migration 0004) and each worker job.
  - One JSON object per log line, and one access line per request with route, status and latency.
  - A redacting filter over messages, extra fields and tracebacks: passwords, tokens, API keys, database URL passwords and card numbers.
- **How it was checked:**
  - 36 tests, then the full suite: 876 passed.
  - By hand on Docker Compose: a failed login with a known password and an agent run with a known access token, neither appearing in any container's logs. The agent run's log lines carried the ID of the request that queued it.
  - Approved by a teammate (Shashi), with all CI checks passing (#84).
- **What changed:**
  - Three redaction defects, found after the approval (E109).
  - A secret-scan allowance for the tests' fake values (E110).
- **Outcome:** accepted with modifications. Gunicorn's and uvicorn's own server messages stay plain text. One unexplained test failure was reported (E112).

### Health, readiness and metrics (CAFIITK-181; NFR-31)

- **Asked for:** `/health`, `/ready` and `/metrics`, used as Docker health checks. The load measurement and the deployment both waited on this.
- **AI produced:**
  - `/ready`, which checks the database and returns 503 with `Retry-After` when it cannot reach it.
  - Prometheus metrics: latency by route template, order outcomes, row-lock waits, agent runs, and database status. Unmatched URLs share one label, so probing cannot create new series.
  - Metrics that report one total across gunicorn's workers.
  - A note for the deployment that `/metrics` has no authentication, so it must not be public.
- **How it was checked:**
  - 9 tests, then the full suite: 818 passed.
  - By hand on Docker Compose: with the database stopped, `/ready` returned 503 and the API turned unhealthy; it recovered without a restart when the database came back.
  - Approved by a teammate (Shashi) (#82).
- **What changed:** a stray file was removed before merge (E111).
- **Outcome:** accepted. One unidentified test failure was reported (E112).

### Strict request validation and safe errors (CAFIITK-183; NFR-22, NFR-23)

- **Asked for:** reject unknown input with a field-level 422, and never show internals in an error response.
- **AI produced:**
  - `extra="forbid"` on the three request bodies that lacked it, and a test that fails if any future body model allows extra fields.
  - Unknown query parameters rejected across the app. `?limt=5` used to fall back silently to the default limit.
  - Unhandled errors answered with a generic JSON 500 and the correlation ID; the traceback goes only to the redacted log.
- **Design choices beyond the requirements:** the 500 is answered in the middleware and not re-raised, because the server would otherwise print the traceback again without redaction.
- **How it was checked:**
  - 18 tests, one using a real failing SQL query. Full suite: 916 passed.
  - By hand on Docker Compose: both 422s, and a 503 with the correlation ID while the database was stopped.
  - Approved by a teammate (Shashi) (#88).
- **What changed:**
  - The route cache (E113).
  - Two hold-sweeper test helpers now assert the 500, because a crash no longer escapes the app.
- **Outcome:** accepted.

### Configure time-of-day discounts (CAFIITK-142, US-17)

- **Asked for:** Administrator endpoints to create, edit and deactivate discount rules. The engine already applied them.
- **AI produced:**
  - `GET`, `POST` and `PATCH /admin/discount-rules`, with problems across fields reported together as field-level 422s.
  - A rule name (migration 0006), since the acceptance criterion names its rules.
  - Audit entries with only the changed fields; an edit that changes nothing writes nothing.
  - The regenerated client. The screens came later, in a separate piece of work.
- **How it was checked:**
  - 35 tests, including TC-US17-AC1 and AC2. Full suite: 978 passed.
  - By hand on Docker Compose: the migration on an existing database, a 60 % rule refused, the AC1 quote, deactivation and the audit rows.
  - Approved by a teammate (Suryansh) (#92).
- **What changed:** a wrong test expectation and a wrong test count (E114).
- **Outcome:** accepted. For E28, the PR proposed keeping the end time excluded and asked reviewers to confirm or object. It was approved with no comment on this, so an explicit team decision is still pending.

### Subsidy for eligible students (CAFIITK-143, US-18)

- **Asked for:** Administrator control of the subsidy settings and of which Students are eligible. The engine already applied the subsidy.
- **AI produced:**
  - `GET` and `PUT /admin/subsidy`, and `PUT /admin/users/{id}/eligibility`.
  - `GET /admin/students`, which was not requested, so that the Administrator can find a Student without knowing their ID.
  - Audit entries with only the changed fields.
  - The regenerated client. The screens came later, in a separate piece of work.
- **Design choices beyond the requirements:**
  - The limits on both settings (E115).
  - Eligibility takes the same lock on the Student's row as order placement, so an order in progress is priced with one value.
  - A deactivated Student can still be marked; a staff account gets a 404.
- **How it was checked:**
  - 43 tests, including TC-US18-AC1. Full suite: 1,021 passed.
  - By hand on Docker Compose: the AC1 quote going from no subsidy to ₹20 off, a changed amount and cap, the refused requests, and the audit rows.
  - Approved by a teammate (Suryansh) (#93).
- **What changed:** a test helper (E116).
- **Outcome:** accepted. The limits are still to be confirmed (E115), and two errors in what the PR said are uncorrected (E118, E119).

### Pricing engine property tests (CAFIITK-187; FR-24, NFR-38)

- **Asked for:** table-driven and property-based tests of the pricing engine that need no database.
- **AI produced:**
  - 10 properties at 300 random examples each, and 16 worked cases.
  - A second implementation of FR-24 using decimal arithmetic, which every generated price must match.
  - Properties for determinism, order independence, no stacking of discounts, the subsidy limits, rounding, and the zero floor. Others check that an extra discount or eligibility never raises the price.
- **How it was checked:**
  - Eight deliberate breakages of the engine, each caught and then undone: seven by the second implementation, one by the zero-floor property.
  - Full suite: 1,047 passed. No hand check, because nothing at runtime changed.
  - Approved by a teammate (Rudransh) (#94).
- **Outcome:** accepted. The engine needed no change, and the tests found no defect in it. The limits of this evidence are in E117.

### Deployment and cost evidence before closing NFR-27, 40, 42 and 43 (CAFIITK-193)

- **Asked for:** once the AWS deployment (CAFIITK-190) and cost tracking (CAFIITK-191) were merged, close the requirement tasks that depended on them.
- **AI produced:**
  - Its own unauthenticated checks of the live stack, without relying on the deployment PR's description: the redirect to HTTPS, the certificate and HSTS, `/health` and `/ready`, `/metrics` hidden, CORS allowing the client origin and refusing another, and the instance unreachable except through CloudFront.
  - An inspection of the production Compose file: one image built from `./backend` runs every service, with the same migration chain.
  - A review of the cost report and its tests before closing NFR-42 and NFR-43.
  - A closing comment on each task naming its drawback:
    - TLS ends at CloudFront (NFR-27);
    - no LLM key on the deployment, so the measured spend is zero and the USD 5 bound is an analysis (NFR-42);
    - the budget alert's email recipient is unverified (NFR-43).
  - The traceability matrix updated to match, and the evidence for each requirement cited in its documents, as the author asked.
- **How it was checked:** every figure in the comments comes from a command run against the live stack or from the cost report. The matrix PR was approved by a teammate (Rudransh).
- **Outcome:** accepted.

### Sprint 3 release (CAFIITK-197)

- **Asked for:** the release PR from `develop` to `main`, then the `d3` tag.
- **AI produced:**
  - A release description built from the merged PR list and Jira, in the same format as the Sprint 2 release. It lists the known gaps.
  - A further PR bringing `main`'s previous release merge commit into `develop`, because the ruleset blocked the release as out of date. That PR changed no files.
  - After the merge, the annotated tag `d3` on `main`'s merge commit, and the release issues closed.
- **What changed:** a re-run of a CI job cancelled the live run, so the checks ran again (E120).
- **How it was checked:** all four required checks passed on the release PR. A teammate (Rudransh) approved both PRs. The tag was confirmed to point at the release merge commit.
- **Outcome:** accepted.

### D3 reports: testing, coverage, concurrency, security, failure, deployment, timeline and project (CAFIITK-193)

- **Asked for:** the documents the brief requires for D3 that were not yet in `Deliverables/`.
- **AI produced:**
  - A full run of both suites at the release commit, with coverage, to give every report one run of record.
  - Seven new reports:
    - unit, integration, system and adversarial tests;
    - coverage;
    - concurrency;
    - the threat model the design document had deferred to D3;
    - failure and recovery;
    - deployment;
    - a timeline with a Gantt chart, and a project report with the Jira dashboard figures.
  - An update to the performance report: the AWS load run, which was still described as pending, is now stated as not done.
- **Team decision:** the author chose one file per brief item, and chose to state that the AWS load run was not done rather than wait for one.
- **What changed:** checking each claim against its source before commit corrected several drafted figures (E121). One merged PR turned out to have no approval of its own: it had been stacked on another PR's branch. The project report says so instead of claiming every PR was reviewed.
- **Team evaluation:** accepted; the PR was approved by a teammate (Rudransh) with no change requests, then merged.

### Keep the session across a reload (Bug CAFIITK-207; NFR-19, NFR-27)

- **Found by:** the author, testing the deployed app before the demo. Every page reload, and every restart of the Android app, sent the user back to the login screen, including from a deep link such as an order page. This was the trade-off the team had accepted in E45 and the threat model's R2.
- **Team decision:** after testing, the team decided the usability cost was too high. It asked for the usual approach that keeps the security benefit while fixing usability.
- **AI produced:**
  - **Access token:** unchanged. It stays in memory and lasts 15 minutes.
  - **Web:**
    - The client sends `X-Token-Transport: cookie` on login, refresh and logout. The server then sets the refresh token as a cookie scripts cannot read: HttpOnly, SameSite=Strict, Secure in production, limited to `/api/v1/auth`, 7 days. It leaves the token out of the response body.
    - The cookie counts only together with that header, which a cross-site page cannot add without a CORS preflight. CORS now allows credentials for the client's origin only.
  - **Android:** the refresh token is kept in Keystore-backed secure storage.
  - **Other clients:** clients that do not send the header get the token in the body as before.
  - **Start-up:**
    - The client restores the session with one refresh, showing a loading screen meanwhile.
    - It then returns the user to the page they were on, if their role may see it. Only a path inside the app is accepted as the return address.
  - **Unchanged:** rotation and reuse detection (T3). Logout and a failed refresh clear the cookie or the stored token.
  - Tests: 10 backend tests, 11 client tests, and the regenerated client.
- **What changed during the work:** two defects in the first version (E122).
- **How it was checked:**
  - Full backend and client suites, client coverage 96.9 %, and the web build.
  - The cookie flow by hand against the local stack: login, a refresh using only the cookie, the old token refused after rotation, and logout clearing the cookie.
- **Documents:** the threat model's T3, R2 and defect list, and E45 above.
- **Team evaluation:** pending review of the PR.
