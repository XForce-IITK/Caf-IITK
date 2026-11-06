# Concurrency Test Report

Caf@IITK, Deliverable 3. Release examined: tag `d3` (`main` at `d97912c`).

## 1. What has to hold

At menu release, many Students order the same item for the same slot at once. Every order for a popular item and an early slot therefore competes for the same two rows: that item's `daily_inventory` row and the slot's `slots` row. The design (SADD §5, §6.2) has to guarantee:

| Requirement | Property |
|---|---|
| NFR-1 | No portion or seat is ever sold twice, however many requests arrive together |
| NFR-2 | The database itself refuses an oversell, even if application code is wrong (CHECK constraints on `allocated` and `booked`) |
| NFR-4 | Deadlocks and serialisation failures are retried (at most 3 times), never surfaced as a 500 |
| NFR-5 | Two conflicting changes to one order (modify and cancel together): exactly one wins |
| NFR-7, FR-32 | A repeated request with the same idempotency key creates one order, never two |
| NFR-13 | All of the above hold across several `caf-api` processes, not just threads in one process |
| ADR-07 | Exactly one `caf-worker` runs the scheduled jobs |

### How the design achieves it

- **Row locks in one fixed order:** `SELECT … FOR UPDATE` on proposals → orders → `daily_inventory` (ascending item id) → `slots` (ascending slot id). Every transaction takes locks in this order, so no two can wait on each other in a cycle.
- **CHECK constraints** `0 <= allocated <= total` and `0 <= booked <= capacity`, as the last line of defence.
- **Short transactions:** reserve → commit → authorise with mockpay (no transaction open, NFR-6) → confirm. Locks are never held across a network call.
- **Idempotency keys** claimed in the same transaction as the order they create.
- **Shared state in PostgreSQL**, not in process memory: rate-limit counters, the LLM daily cap, and the worker's advisory lock. A limit therefore holds however many processes run.

## 2. How it was tested

All concurrency tests run against **real PostgreSQL 16** in a testcontainers container, never SQLite or mocks. The tests that need several processes use the `live_stack` fixture: it starts **two separate `caf-api` processes and mockpay**, and sends real HTTP to both. Concurrent requests come from thread pools (`concurrent.futures.ThreadPoolExecutor`) or, for the rush, from the load generator in `tests/loadgen.py`.

## 3. Tests and results

| Test | Scenario | Pass condition | Requirement | Result |
|---|---|---|---|---|
| `test_order_rush.py::test_tc_us30_ac1_two_hundred_concurrent_orders_never_oversell` | 200 Students order at once, against 50 portions and 30 seats, spread over two API processes. Repeated for **10 consecutive runs** | Every run: exactly 30 accepted (201), 170 refused (409), 20 portions left, 0 seats left | NFR-1, NFR-13 | Pass |
| `test_order_rush.py::test_tc_us30_ac2_database_refuses_a_count_the_application_should_never_write` | The application's own check is skipped and a direct write tries to exceed the counts | The CHECK constraints refuse it; the counts stay at total 50, allocated 50, booked 30 | NFR-2 | Pass |
| `test_order_rush.py::test_tc_us30_ac3_concurrent_modify_and_cancel_exactly_one_succeeds` | On each of 30 accepted orders, a modify and a cancel arrive together | For every order exactly one wins (modify wins + cancel wins = 30); no inconsistent state | NFR-5 | Pass |
| `test_order_rush.py::test_tc_us30_ac4_mixed_workload_has_no_unhandled_deadlock` | **60 seconds** of mixed create, modify and cancel across two processes | No unhandled deadlock or 500; every action type (place, modify, cancel) succeeded at least once | NFR-4, NFR-13 | Pass |
| `test_order_retry.py` (3 tests) | A transaction hits a deadlock or serialisation failure | Retried with back-off; gives up after 3 retries; other database errors are not retried | NFR-4 | Pass |
| `test_idempotency.py::test_tc_us25_ac3_twenty_concurrent_duplicates_create_one_order` | 20 identical `POST /orders` with the same key, at once | All 20 get 201 with the **same** order id; one order exists | NFR-7, FR-32 | Pass |
| `test_order_cancel.py::test_tc_us28_ac5_two_concurrent_cancels_record_exactly_one_refund` | Two cancels of one order at once | One 200, one 409; exactly one refund row; the portions and seat are released once | FR-37, FR-39 | Pass |
| `test_order_cancel.py::test_concurrent_retries_of_one_cancel_return_the_same_result` | Retries of one cancel (same key) at once | Every retry gets the same answer | NFR-7 | Pass |
| `test_proposal_decisions.py::test_concurrent_decisions_exactly_one_succeeds` | Two Administrators approve or reject one proposal at once | Exactly one decision succeeds; the other gets 409 | FR-56 | Pass |
| `test_inventory_set.py::test_concurrent_first_sets_create_one_row` | 8 Administrators set one item's first daily inventory at once | All succeed, one row exists, and exactly one audit entry records the creation | FR-14, FR-47 | Pass |
| `test_slots_capacity.py::test_a_cut_waiting_on_a_booking_sees_the_new_seat` | A capacity cut arrives while a booking holds the slot's lock | The cut waits for the lock, then sees the new booking and is refused (409), never decided on stale data | FR-18 | Pass |
| `test_rate_limits.py::test_nfr21_failed_logins_are_limited_across_api_processes` | 20 parallel wrong-password guesses, spread over two API processes | Exactly 5 are checked; the rest get 429 | NFR-21, NFR-13 | Pass |
| `test_rate_limits.py` (account and address limits) | Guesses spread over many addresses for one account, or many accounts from one address | The per-account and per-address limits each hold | NFR-21 | Pass |
| `test_llm_client.py::test_the_cap_is_shared_across_processes_and_holds_under_concurrency` | 12 LLM clients call at once against a daily cap of 5 | Exactly 5 provider calls are made; the rest are refused as capped | NFR-42 | Pass |
| `test_worker.py` (leader election, 4 tests) | Several `caf-worker`s start; the leader stops or loses its lock connection | Only one runs the jobs; a second cannot start while one leads; a follower takes over; a leader whose lock connection drops stops | ADR-07 | Pass |

**Result: all pass** on the release, in the full suite run of §4.

## 4. Run of record

The full backend suite was run at `d97912c` on the release day. These concurrency tests are part of it, and the same tests pass in CI on every PR (required check "Backend lint, type-check and tests"). See `Test-Report.md` §2 for the run's totals.

## 5. Defects and findings

- **No oversell, deadlock or double refund** was found by these tests in Sprint 3.
- **Lock contention was a performance problem, not a correctness one.** Under the rush, orders queued on the hot rows. CAFIITK-189 shortened the time the lock is held: the lock wait fell from 190 ms to 15 ms (`Performance-Report.md` §3.5, §5). The AC1 test above was re-run after that change, and it still passes.
- **Rate limit race, designed out:** a login attempt takes its place in the window *before* the password is checked. Checking first and counting afterwards would let a burst of parallel guesses all pass the check. The cross-process test above proves this holds.

## 6. Limits of this testing

- The concurrency tests run on one machine (testcontainers). The multi-process tests use two API processes, not the two-worker gunicorn setup on EC2 against RDS. No concurrency or load test was run on AWS (`Performance-Report.md` §4).
- Thread pools in one test process create the concurrency. Python threads interleave, but cannot start 200 requests at exactly the same instant. The 10 repeated runs of AC1 are there to make a lucky interleaving unlikely to hide a bug.
