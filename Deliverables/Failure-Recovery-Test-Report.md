# Failure and Recovery Test Report

Caf@IITK, Deliverable 3. Release examined: tag `d3` (`main` at `d97912c`).

This report covers what happens when something fails partway through: the database stops, a process crashes mid-order, the payment provider declines or times out, the LLM is unreachable, or a worker dies. For each failure it gives the expected behaviour (SADD §6.2), the test that proves it, and the result.

## 1. Requirements

| Requirement | What must hold |
|---|---|
| NFR-3 | Every multi-row write is all-or-nothing: no counter, order or payment is left half-written |
| NFR-6 | No network call (payment provider, LLM) while a database transaction is open |
| NFR-14 | A failed or timed-out payment releases the reserved portions and seat |
| NFR-15 | After a crash between reserve and confirm, the hold sweeper releases what was reserved |
| NFR-16 | If the database is lost, the API answers 503 with `Retry-After`, and recovers by itself when the database returns |
| NFR-17 | Agent failures never block or slow ordering and the kitchen |
| NFR-18 | The client retries create, modify and cancel safely, reusing its idempotency key |
| ADR-07 | If the worker leader dies, another worker takes over the jobs |

## 2. Fault injection at every SQL statement (NFR-3, NFR-6)

`backend/tests/test_failure_injection.py` (CAFIITK-184, PR #77) is the core of this report.

**Method.** Each write operation is run once for every SQL statement it issues, with a fault injected at that statement. After each fault, two things must hold:
1. The database is exactly as it was when the faulted transaction began: nothing of it was written, and nothing else was committed after it.
2. An operation made of several transactions (reserve, authorise, confirm) may stop at a committed boundary, but only at one the system recovers from. Once the hold sweeper and the payment outbox have run, every counter matches the orders that hold it, and no order, modification or payment is left pending.

`test_the_injector_does_see_a_partial_write` proves the injector itself works: without the transaction it would detect a partial write.

| Operation faulted at every statement | Test | Result |
|---|---|---|
| Place an order | `test_tc_nfr3_order_creation_is_all_or_nothing` | Pass |
| Release after a declined payment | `test_tc_nfr3_payment_failure_release_is_all_or_nothing` | Pass |
| Modify an order | `test_tc_nfr3_order_modification_is_all_or_nothing` | Pass |
| Cancel an order (Student) | `test_tc_nfr3_order_cancellation_is_all_or_nothing` | Pass |
| Cancel an order (Administrator) | `test_tc_nfr3_admin_cancellation_is_all_or_nothing` | Pass |
| Expire a hold (sweeper) | `test_tc_nfr3_hold_expiry_is_all_or_nothing` | Pass |
| Apply an approved agent proposal | `test_tc_nfr3_proposal_execution_is_all_or_nothing` | Pass |

**NFR-6.** The payment gateway and the LLM provider are wrapped in spies that record whether any application connection was checked out when they were called. `test_tc_nfr6_no_payment_call_with_a_transaction_open` and `test_tc_nfr6_no_llm_call_with_a_transaction_open` both pass. In addition, `PaymentGateway` itself refuses to run inside an open transaction (`test_gateway_refuses_to_run_inside_an_open_transaction`).

## 3. Database loss (NFR-16, US-32)

`backend/tests/test_db_down.py` stops and restarts the PostgreSQL test container under a running API.

| Scenario | Expected | Test | Result |
|---|---|---|---|
| Database stopped | 503 with `Retry-After`, answered within 5 s, not a hang or a 500 | `test_tc_us32_ac1_database_stopped_gives_503_with_retry_after_within_5_s` | Pass |
| Database dies in the middle of an order | Only a hold is left, and the sweeper releases it | `test_tc_us32_ac1_dying_mid_order_leaves_only_a_hold_the_sweeper_releases` | Pass |
| Database restarted | Ordering resumes within 30 s, without restarting the API | `test_tc_us32_ac2_ordering_resumes_within_30_s_of_a_restart_without_an_app_restart` | Pass |
| Worker during an outage | Waits it out, then becomes leader | `test_a_worker_waits_out_an_outage_then_becomes_leader` | Pass |
| A statement error, not a lost connection | Not turned into a 503 | `test_only_connection_failures_count_as_the_database_being_down`, `test_a_statement_error_is_not_turned_into_a_503` | Pass |

It was also demonstrated by hand on Docker Compose, by stopping and starting the `db` service (PR #73).

## 4. Crash between reserve and confirm (NFR-15, US-24)

`backend/tests/test_hold_sweeper.py` simulates a crash with a gateway whose `authorise` raises. The reservation is committed, and no payment result is ever recorded.

| Scenario | Expected | Test | Result |
|---|---|---|---|
| A crashed order | Expires within hold expiry + sweep interval; portions and seat released | `test_tc_us24_ac1_a_crashed_order_expires_within_hold_expiry_plus_sweep_interval` | Pass |
| Worker restart | Recovers stale holds at start-up | `test_tc_us24_ac1_the_worker_recovers_holds_at_start_up` | Pass |
| Payment approved after the hold expired | The order stays failed and the authorisation is voided | `test_tc_us24_ac2_a_late_approval_leaves_the_order_failed_and_is_voided`, and against real mockpay `test_tc_us24_ac2_against_real_mockpay_the_late_approval_is_refused` | Pass |
| Other orders | Accepted and later orders are untouched by the sweep | `test_tc_us24_ac3_accepted_and_later_orders_are_untouched`, `test_a_fresh_pending_order_is_not_expired` | Pass |
| A modification left pending | Its holds are released and the order stays as it was before | `test_an_expired_modification_releases_its_holds_and_leaves_the_order_as_before`, `test_a_late_approval_of_an_expired_modification_is_never_refunded_against` | Pass |
| A void or refund the provider did not acknowledge | The payment outbox retries until it is acknowledged | `test_the_outbox_retries_a_void_until_the_gateway_acknowledges_it`, `test_the_outbox_delivers_a_refund_the_gateway_did_not_acknowledge` | Pass |

It was also demonstrated by hand on Docker Compose, by killing `caf-api` mid-payment (PR #68).

## 5. Payment failure (NFR-14, US-23)

| Scenario | Expected | Test | Result |
|---|---|---|---|
| Declined | Portions and seat released | `test_order_payment_failure.py::test_tc_us23_ac1_declined_payment_releases_the_portions_and_seat` | Pass |
| Timed out (mockpay never answers; the test sets P-PAY_TIMEOUT to 0.5 s) | The gateway waits the full timeout, then the portions and seat are released within the NFR-14 deadline | `test_tc_us23_ac2_timed_out_payment_releases_the_portions_and_seat` | Pass |
| Approval arrives after the timeout | The order is not accepted; the authorisation is voided | `test_approval_that_arrives_after_the_timeout_does_not_accept_the_order`, `test_payment_gateway.py::test_void_after_a_timeout_stops_a_late_approval` | Pass |
| mockpay unreachable or refuses | Treated as a failure, never as approved | `test_unreachable_mockpay`, `test_authorise_rejected_by_mockpay_is_not_treated_as_approved`, `test_refund_refused_by_mockpay_raises` | Pass |

## 6. Agent and LLM failure (NFR-17, US-43)

| Scenario | Expected | Test | Result |
|---|---|---|---|
| LLM unreachable | Heuristic report within 5 s | `test_agent_run.py::test_tc_us43_ac1_unreachable_llm_gives_a_heuristic_report_within_5_s` | Pass |
| LLM slow | Ordering is not slowed | `test_tc_us43_ac1_a_slow_llm_does_not_slow_ordering` | Pass |
| Daily cap reached | Heuristic only | `test_tc_us43_ac2_daily_cap_reached_uses_the_heuristic` | Pass |
| Repeated LLM failures | The circuit breaker opens, then recovers; a failed trial reopens it | `test_llm_client.py::test_the_breaker_opens_after_repeated_failures_and_recovers`, `test_a_failed_trial_reopens_the_breaker` | Pass |

## 7. Worker failure (ADR-07)

| Scenario | Expected | Test | Result |
|---|---|---|---|
| Leader stops | A follower takes over | `test_worker.py::test_a_follower_takes_over_when_the_leader_stops` | Pass |
| Leader loses its lock connection | It stops running jobs | `test_losing_the_lock_connection_stops_the_leader` | Pass |
| A job raises | It keeps being scheduled | `test_a_failing_job_keeps_being_scheduled` | Pass |
| SIGTERM | The worker process stops cleanly | `test_worker_process_starts_and_stops_on_sigterm` | Pass |

## 8. Client retries (NFR-18)

`app/test/interceptors_test.dart`:
- a briefly unavailable server (502/503/504) or a network failure is retried with back-off;
- it gives up after three retries, and honours a longer `Retry-After`;
- a sold-out answer is final and is not retried;
- a request without an idempotency key is never retried.

On the server, `test_idempotency.py` and `test_order_cancel.py::test_concurrent_retries_of_one_cancel_return_the_same_result` prove that a retried request with the same key returns the first result instead of acting twice. All pass.

## 9. Result

**Every failure and recovery test passes** on the release (full suite run: `Test-Report.md` §2). No defect was found by these tests in Sprint 3; they were written alongside the code they test (CAFIITK-149, 157, 184).

## 10. Limits

- Failures were injected on testcontainers PostgreSQL and on the Docker Compose stack, not on AWS. RDS failover (Multi-AZ is off on the free tier) was not tested.
- The payment provider is mockpay; a real provider's failure modes (partial captures, chargebacks) are out of scope.
- Network partitions between `caf-api` and the database are simulated by stopping the container, not by dropping packets.
