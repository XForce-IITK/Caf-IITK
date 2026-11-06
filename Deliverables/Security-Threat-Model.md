# Security and Threat Model Report

Caf@IITK, Deliverable 3. This is the full threat model that SADD §6.3 deferred to D3. It also reports the security test campaign (CAFIITK-185) and the defects it found.

Release examined: tag `d3` (`main` at `d97912c`).

## 1. Scope

| Asset | Why it matters |
|---|---|
| Orders, holds and refunds | Money and food: a forged or duplicated order, or a refund paid twice, is a direct loss |
| Inventory and slot counters (`allocated`, `booked`) | Overselling breaks the core promise of the system (FR-30, NFR-1) |
| Accounts and credentials | Students, Kitchen Staff and Administrators; a stolen Administrator account controls prices, stock and staff |
| Price, discount and subsidy rules | Changing them changes what every Student pays |
| Audit log | The record of every consequential change; useless if it can be edited |
| Agent proposals | The agent may only propose; a proposal that applied itself would bypass the Administrator |
| Secrets | JWT signing key, database passwords, LLM API key |

### Trust boundaries

```
Browser / Android app ──HTTPS──▶ CloudFront ──HTTP (CloudFront prefix list only)──▶ nginx ──▶ caf-api ──▶ RDS PostgreSQL
                                                                                     caf-worker ─┘    │
                                                                       mockpay ◀── caf-api            │
                                                                       LLM API ◀── agent (caf_agent role, views only)
```

1. **Client ↔ API:** nothing from the client is trusted. The route guard in the client is for usability only; the server checks every permission.
2. **API ↔ database:** application transactions run as `caf_app` (migration 0005), and the agent runs as `caf_agent` (0002, 0007). Neither role can change the audit log.
3. **API ↔ payment provider and LLM:** both are called only with no database transaction open (NFR-6). LLM output is treated as untrusted input.
4. **Internet ↔ instance:** only CloudFront can reach port 80. The API (8000) and mockpay (8001) are not published.

## 2. Threats and controls

STRIDE category: **S**poofing, **T**ampering, **R**epudiation, **I**nformation disclosure, **D**enial of service, **E**levation of privilege. T1–T9 are the SADD §6.3 threats; T10–T15 were added for D3.

| # | Threat | STRIDE | Control | Verified by | Status |
|---|---|---|---|---|---|
| T1 | A Student reads or changes another Student's order (IDOR) | I, T | The repository query filters by owner; another user's order answers 404, so its existence is not revealed | `test_a_student_cannot_see_or_change_another_students_order` | Mitigated |
| T2 | Privilege escalation: a Student or Kitchen user calls Administrator actions | E | Every route declares its permission (SRS Table 4.1-A). The role comes from the database row of the verified token's user, never from the request. A role change applies on the next request | `test_each_role_reaches_exactly_its_permitted_routes` (all 46 routes × 4 caller types), `test_a_role_claim_cannot_raise_privileges`, `test_registration_cannot_choose_a_role`, `test_permissions.py`, `test_authorisation.py` | Mitigated |
| T3 | Token theft, forgery or replay | S | 15-minute HS256 access tokens. Refresh tokens are random, stored hashed, rotated on use, revoked on logout, and live 7 days. Presenting an already-rotated token is treated as theft, and every refresh token of that user is revoked. Production refuses a default or short JWT secret. HTTPS only, with HSTS | `test_tokens.py`, `test_forged_or_misused_tokens_get_401`, `test_a_refresh_token_is_not_accepted_as_an_access_token`, `test_a_logged_out_refresh_token_cannot_be_used`, `test_logging_out_with_someone_elses_refresh_token_does_not_revoke_it`, `test_a_deactivated_account_is_refused_with_a_valid_token` | Mitigated (residual R1, R2) |
| T4 | Credential brute force | S | Argon2id password hashes. Failed logins are limited per account and per client IP, with counters in PostgreSQL shared by every API process; an attempt takes its slot before the password is checked. Behind CloudFront, nginx passes on only the address CloudFront appended, so a client cannot choose the IP that is counted | `test_rate_limits.py` (including the cross-process test on two API processes), `test_security.py`; on AWS, a spoofed `X-Forwarded-For` was ignored (PR #106) | Mitigated |
| T5 | Injection: SQL, mass assignment, unknown fields | T | ORM bound parameters only. Every request body model forbids unknown fields, and unknown query parameters are refused with a field-level 422. NUL characters are refused in body text and query text | `test_sql_in_a_login_email_is_just_a_failed_login`, `test_request_safety.py` (NFR-22), `test_an_order_cannot_set_server_owned_fields`, `test_nul_text.py` | Mitigated (two defects found and fixed, §4) |
| T6 | Prompt injection or agent misuse | T, E | The agent connects as `caf_agent`: SELECT on five `agent_*` views, INSERT on proposals and agent logs, nothing else. Only registered tools can be called; every argument and output is validated. Free text from tools is data, never instructions. Proposals take effect only through `ProposalService` under an Administrator's identity | `test_agent_authority.py` (TC-US41-AC1..AC3), `test_tc_us41_ac2_instructions_in_an_item_description_cause_no_mutation`, `test_managed_database_roles.py` | Mitigated |
| T7 | Secret leakage | I | Secrets come from environment variables; the production `.env` exists only on the instance (`chmod 600`). gitleaks scans the full history on every PR. A logging filter removes passwords, tokens and keys. The LLM key never reaches the client. 422 responses do not echo the submitted password | gitleaks CI job, `test_observability.py`, `test_tc_us38_ac4_no_password_token_or_secret_appears_in_results`; CAFIITK-199 (§4) | Mitigated |
| T8 | Audit tampering, or denying an action took place | T, R | `caf_app` has no UPDATE or DELETE on `audit_log`, and no API route changes it. Audit rows are written in the same transaction as the change, so a change cannot commit without its record. Failed logins are audited too (FR-47) | `test_tc_us38_ac3_the_application_role_cannot_change_an_audit_entry`, `test_no_api_route_changes_the_audit_log`, `test_the_audit_log_stays_append_only` (on an RDS-like non-superuser login), `test_login_audit.py` | Mitigated (one defect found and fixed, §4) |
| T9 | Information leakage through errors | I | A global handler turns any unhandled error, database error or mockpay error into a generic 500 carrying only the correlation ID; the details go to the log | `test_request_safety.py` (NFR-23, 9 tests) | Mitigated |
| T10 | Paying less than the price, or exceeding quantity limits | T | The server prices every order from its own rules. A client-sent amount that does not match is refused. Quantity limits apply to the order's total per item, not per line | `test_paying_less_than_the_price_is_refused`, `test_splitting_an_item_over_lines_does_not_bypass_the_quantity_limit`, `test_a_quantity_above_p_max_qty_is_refused` | Mitigated |
| T11 | Reusing someone else's idempotency key to read or repeat their order | I, T | Idempotency keys are scoped to the user who sent them | `test_another_students_idempotency_key_does_not_return_their_order`, `test_hostile_idempotency_keys_never_cause_a_server_error` | Mitigated |
| T12 | Hostile or malformed input crashing the API | D | Strict validation; oversized and non-JSON bodies are refused; ids are range-checked | Fuzz tests over every route's bodies, query parameters, path parameters and idempotency keys (`test_hostile_*_never_cause_a_server_error`), `test_an_oversized_body_is_rejected_without_a_server_error` | Mitigated (CAFIITK-200, 203, 204 fixed) |
| T13 | Order flooding by one Student | D | Order create, modify and cancel are rate-limited per Student; at most P-MAX_ACTIVE unfinished orders per Student per date | `test_rate_limits.py`, CAFIITK-151 tests | Mitigated |
| T14 | Cross-origin requests from another site | S | CORS allows only the client's own origin in production | `test_cors.py`; on AWS, a preflight from another origin gets 400 (CAFIITK-107) | Mitigated |
| T15 | Direct access to the instance, bypassing HTTPS | I, T | Port 80 accepts only CloudFront's origin-facing prefix list; 8000 and 8001 are not published; `/metrics` is not served publicly | Checked on the deployed stack on 6 Nov 2026 (CAFIITK-107, PR #107) | Mitigated (residual R1) |

## 3. Security test campaign (CAFIITK-185)

The campaign ran against the complete system once every feature had merged (`backend/tests/test_security_campaign.py`, PR #97).

- **Access control matrix:** 46 routes, each mapped to its permission, to "any logged-in user", or to "public". `test_every_route_is_in_the_matrix` fails if a new route is added without an entry. Each route is called by an anonymous caller, a Student, Kitchen Staff and an Administrator, and must answer exactly as the matrix says.
- **Authentication:** forged, expired, wrongly signed and unsigned tokens; refresh tokens used as access tokens; tokens of deactivated accounts; logged-out refresh tokens.
- **Business logic:** server-owned fields, underpayment, quantity splitting, other users' idempotency keys.
- **Fuzzing:** hostile values in every body field, query parameter, path parameter and idempotency key of every route. The values are: nulls and wrong types; numbers at and beyond the 32- and 64-bit limits; 100,000-character strings; NUL characters; SQL fragments; impossible dates and times; the nil UUID; operator objects such as `{"$gt": ""}`; deeply nested bodies. The only pass condition is "no 5xx".

Results: 29 tests in the campaign file. All pass on the release, and so does the full suite (see `Test-Report.md`).

## 4. Defects found

| Bug | Found by | Defect | Fix |
|---|---|---|---|
| CAFIITK-199 | Security testing | 422 validation responses echoed the rejected password back to the client (NFR-20) | Password values are removed from validation errors (PR #69) |
| CAFIITK-200 | Adversarial testing | A NUL character in request text gave a 500 (PostgreSQL refuses NUL in text) | A `NoNul` validator on every text field; 422 instead (PR #74) |
| CAFIITK-203 | Adversarial testing | A NUL in a text query parameter (audit search, admin orders, student search) gave a 500 | The same validator on query parameters (PR #96) |
| CAFIITK-204 | Adversarial testing | An audit-search `before_id` beyond the bigint range gave a 500 | The parameter is bounded at 2⁶³−1; a field-level 422 instead (PR #96) |
| CAFIITK-205 | Code review | Failed logins were not written to the audit log (FR-47) | `LOGIN_FAILED` rows with the client IP and whether the account exists. Rate-limited attempts (429) are not audited, by decision (PR #101) |

All five have regression tests and are closed in Jira.

## 5. Residual risks

| # | Risk | Why it is accepted |
|---|---|---|
| R1 | TLS ends at CloudFront; the CloudFront → EC2 hop is plain HTTP | Let's Encrypt could not issue a certificate for any hostname that resolves on the campus network (PR #106). Port 80 accepts only CloudFront's prefix list, which limits who can reach that hop |
| R2 | Access and refresh tokens are kept in the client's memory; any script running in the page (XSS) could read them | Not kept in browser storage, so reloading the page logs the user out. Flutter Web renders to a canvas, not to HTML built from user data. No XSS testing was done |
| R3 | HS256 uses one shared secret for signing and checking tokens | Only `caf-api` issues and checks tokens. Production refuses a default or short secret |
| R4 | mockpay is a simulated payment provider | The course project has no real payment integration; the gateway contract (timeouts, voids, refunds, the outbox) is what was tested |
| R5 | No WAF, and no denial-of-service protection beyond CloudFront's defaults and the per-account, per-IP and per-Student limits | The free-tier budget rules out a paid WAF |
| R6 | The deployed agent runs without an LLM key, so prompt-injection defences have been exercised in tests, not against a live model on AWS | The tests inject instructions through tool results and check that nothing changes (TC-US41-AC2). A real LLM run was recorded locally in D2 |
| R7 | The AWS budget alert's email recipient is unverified, so an alert would not be delivered | The Free account plan cannot be billed (`Cost-Report.md` §3) |
