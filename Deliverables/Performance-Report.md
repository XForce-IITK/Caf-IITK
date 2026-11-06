# Caf@IITK Performance Report

Latency, throughput and agent run time against NFR-8 to NFR-12 (SRS §4).
- Measurement: CAFIITK-188, sections 1 and 2.
- Bottleneck analysis, with before-and-after numbers: CAFIITK-189, section 3.
- The AWS run planned as section 4 was not done for Deliverable 3 (see §4). The laptop runs in sections 2, 3 and 5 are therefore the numbers of record.

## 1. How it was measured

`backend/tests/perf.py` drives a running `caf-api` over real HTTP. Each workload seeds its
own Students, items and slots, sends its requests, and records every request's latency as
the client sees it: connection, queueing and server time together. Percentiles are
nearest-rank over every request. A 409 or 422 is a designed rejection (sold out, slot
full, price changed), not an error; any other non-2xx, or no response at all, is an error.

Before and after each workload, the harness scrapes `GET /metrics` (CAFIITK-181) and
reports the difference: requests per route with their server-side mean and p95, and the
time spent in `SELECT … FOR UPDATE` per locked table. Histogram p95 values are bucket
bounds, not exact figures.

mockpay is set to approve with no delay, so order latency excludes the mock payment time
(NFR-8). `tests/test_perf.py` runs every workload at 5 % scale in CI to prove the harness
works and counts correctly; it does not check the targets.

| Workload | What it does | NFR target |
|---|---|---|
| NFR-8 | 50 concurrent clients place 200 orders for one item and one slot | p95 ≤ 500 ms, p99 ≤ 1 s |
| NFR-9 | 100 concurrent users read the menu, slots, order history and kitchen queue for 30 s | p95 ≤ 200 ms per read |
| NFR-10 | Open loop: one order every 50 ms (20/s) for 60 s, whatever the responses | error rate < 1 % |
| NFR-11 | One planning run, timed as `caf-worker` runs it (`AgentService.run_next`) | ≤ 60 s with the LLM; ≤ 5 s heuristic |
| NFR-12 | Design day (500 Students, 15 items of 100, 10 slots of 30): 200 orders by 50 clients within 60 s, with 100 readers alongside | NFR-8 and NFR-9 targets hold |

NFR-10's 1,200 orders are spread round-robin over three items and three slots, because the
schema caps an item at 500 portions a day (`ck_daily_inventory_total_range`).

**Run conditions.** Run 1 (section 2) taught us three conditions without which the numbers
mislead. Every run from section 3 on meets all three:
- **Each workload starts from an empty database** (`--fresh`). Orders stay ACCEPTED, and
  the kitchen queue lists the open orders of the next two slots. Without a reset,
  NFR-12's kitchen reads carried NFR-10's 1,200 orders, about 40 times what a 30-seat
  design slot holds.
- **The load client runs in a container on the Compose network.** On Docker Desktop for
  Windows, the port proxy from the host into the VM dropped a few connections under this
  load. The client saw these as "no response", and the server never saw a failure.
- **The laptop is on mains power.** One run made on battery, on the Balanced power plan,
  came out 20–40 % slower than an identical run on mains.

Even under these conditions, two runs of the same build differ by up to about 30 % at the
tail. Before and after are therefore compared over interleaved repeats (A, B, A, B), not
over single runs.

## 2. Run 1: Docker Compose on a laptop (CAFIITK-188, first pass)

This first pass broke all three run conditions above. Its numbers are kept as a record,
but section 3's base runs replace them as the baseline.

**Environment.**
- Commit: `1331969` (`develop`, 3 Nov 2026).
- Stack: Docker Compose, with the `api`, `worker`, `mockpay` and `db` (PostgreSQL 16) containers.
- `caf-api` config: gunicorn with 2 Uvicorn workers. SQLAlchemy's default pool is 5 + 10 overflow per process; PostgreSQL `max_connections` is 100.
- Host: AMD Ryzen 5 5500U (6 cores, 12 threads) with 13.8 GB RAM, running Windows 11. Docker Desktop 29.8 with a 12-CPU, 6.7 GB VM.
- The load generator ran on the same machine as the stack, so the two compete for CPU.

**Command** (from `backend/`):

```bash
CAF_JWT_SECRET=<the stack's secret> PYTHONPATH=. .venv/Scripts/python.exe tests/perf.py \
    --base-url http://localhost:8000 --mockpay-url http://localhost:8001 \
    --database-url postgresql+psycopg://caf:caf@localhost:5432/caf --json perf-run.json
```

### 2.1 Results against the targets (client side)

| Workload | Target | Requests | p50 ms | p95 ms | p99 ms | Errors | Met |
|---|---|---|---|---|---|---|---|
| NFR-8: orders, one item and slot | p95 ≤ 500 ms, p99 ≤ 1 s | 200 | 2224 | 3605 | 3952 | 0 | **no** |
| NFR-9: menu | p95 ≤ 200 ms | 658 | 998 | 2141 | 2544 | 0 | **no** |
| NFR-9: slots | p95 ≤ 200 ms | 585 | 1131 | 2197 | 2587 | 0 | **no** |
| NFR-9: order history | p95 ≤ 200 ms | 609 | 1154 | 2151 | 2535 | 0 | **no** |
| NFR-9: kitchen queue | p95 ≤ 200 ms | 595 | 1233 | 2249 | 2845 | 0 | **no** |
| NFR-10: 20 orders/s for 60 s | error rate < 1 % | 1200 | 105 | 5263 | 6723 | 0 (0.00 %) | yes |
| NFR-11: agent run, heuristic | ≤ 5 s | 1 run | | | | | yes (0.15 s, SUCCEEDED) |
| NFR-11: agent run, LLM | ≤ 60 s | — | | | | | not measured |
| NFR-12: orders | p95 ≤ 500 ms, p99 ≤ 1 s; within 60 s | 200 | 6696 | 8974 | 10884 | 0 | **no** (burst took 45.1 s) |
| NFR-12: menu | p95 ≤ 200 ms | 482 | 1861 | 4632 | 5441 | 0 | **no** |
| NFR-12: slots | p95 ≤ 200 ms | 460 | 1704 | 4629 | 5399 | 0 | **no** |
| NFR-12: order history | p95 ≤ 200 ms | 497 | 1741 | 4554 | 5426 | 0 | **no** |
| NFR-12: kitchen queue | p95 ≤ 200 ms | 455 | 2343 | 4940 | 6100 | 0 | **no** |

NFR-10 sustained 19.1 accepted orders per second, and every order was accepted. Its p95 is
not an NFR-10 target, but it shows a queue building up during the minute.

NFR-11's LLM run was not measured because no `CAF_LLM_API_KEY` is configured in this
environment. The heuristic fallback (FR-59) was timed instead. No key is configured
on the AWS deployment either (§4), so the LLM run was not measured for D3; NFR-11 was
closed on direct verification (`Requirements-Traceability.md`).

### 2.2 Server side (from /metrics)

| Workload | Route or lock | Count | Server mean ms | Server p95 (bucket) |
|---|---|---|---|---|
| NFR-8 | `POST /api/v1/orders` | 200 | 1985 | ≤ 5000 |
| NFR-8 | lock wait: `daily_inventory` | 200 | 1017 | ≤ 2500 |
| NFR-8 | lock wait: `slots`, `orders`, `users` | 200 each | 2–4 | ≤ 25 |
| NFR-9 | `GET /api/v1/menu` | 658 | 1156 | ≤ 2500 |
| NFR-9 | `GET /api/v1/slots` | 585 | 1218 | ≤ 2500 |
| NFR-9 | `GET /api/v1/orders` | 609 | 1208 | ≤ 2500 |
| NFR-9 | `GET /api/v1/kitchen/queue` | 595 | 1367 | ≤ 2500 |
| NFR-9 | `GET /ready` (Docker health check) | 3 | 1050 | ≤ 2500 |
| NFR-10 | `POST /api/v1/orders` | 1200 | 1280 | ≤ 7500 |
| NFR-10 | lock wait: `daily_inventory` | 1200 | 345 | ≤ 2500 |
| NFR-12 | `POST /api/v1/orders` | 200 | 6419 | ≤ 10000 |
| NFR-12 | `POST /api/v1/quotes` | 200 | 3349 | ≤ 7500 |
| NFR-12 | reads (menu, slots, history, kitchen) | 455–497 each | 2227–2758 | ≤ 5000 |
| NFR-12 | lock wait: `daily_inventory` / `slots` | 200 each | 314 / 103 | ≤ 2500 / ≤ 500 |

**Client time vs server time.** The server's mean is close to the client's p50 for every
route, which leaves little room for client-side queueing or connection setup. The time is
spent inside `caf-api`, between the request arriving and the response leaving.

## 3. Bottleneck analysis and optimisation (CAFIITK-189)

### 3.1 Method

The CAFIITK-189 task named three things to try:
- a conditional atomic UPDATE for the menu-release hot row (SADD 6.5);
- short-TTL caching of the menu and slots;
- connection-pool sizing.

Its rule was to keep only what measurably helps. Before changing anything, `caf-api` was
profiled in-process with yappi, which samples every thread. The profiles ran on clean
data under the NFR-9 read load and the NFR-8 order rush, with the run conditions of section 1.

Each candidate was then built into its own image and measured under the same Compose
stack. The comparison swapped the `api` image and its settings, while the database, the
worker, mockpay and the load client stayed the same.

- **Base:** `develop` at `1331969`. SQLAlchemy's default pool (5, plus up to 10 overflow per process) and 2 gunicorn workers.
- **Final:** this branch, with the changes in 3.3, 2 workers and a fixed pool of 5.

### 3.2 What the profiles and metrics showed

1. **Connection churn.** Overflow connections are closed as soon as they are returned. Under
   load, nearly every pool checkout therefore opened a new database connection, each with a
   TCP handshake, a forked backend and a SCRAM exchange. In the read profile, opening
   connections was the largest single item of CPU (358 connections for 129 requests).
   PostgreSQL's own counter agreed: the base build opened **442** connections during the
   30 s NFR-9 load.
2. **The hot row was held for a whole transaction.** A placement locked its item's
   `daily_inventory` row and then, under that lock, did the following:
   - locked the slot;
   - priced the order (the quote runs its own queries);
   - inserted the order, its lines, the price snapshot, the payment and the transition;
   - wrote the audit rows;
   - committed.

   That is about 15 database round trips. Every placement for that item waits for this
   lock, so its length sets the pace of a rush. In NFR-8, the mean wait for it was 1.1 s.
3. **The lock holder also waits for the GIL.** Each round trip under the lock gives up the
   process's GIL and must win it back from every other busy thread in that process. More
   concurrent work per process therefore means a longer hold. The pool-size sweep in 3.4
   bears this out: the bigger the pool, the longer the hot-row wait.
4. **The API processes are the ceiling.** On clean data, with the final build, the `api`
   container ran at about 250 % CPU under the read load: two gunicorn processes, each close
   to one core. PostgreSQL was at 25–32 % and the load client at about 30 %. The server's
   own time per request (`/metrics`) is close to the client's, so requests wait inside
   `caf-api`, not in the network or the client.

### 3.3 Changes kept

| Change | Where | Evidence (3.4, 3.5) |
|---|---|---|
| Fixed pool with no overflow, `CAF_DB_POOL_SIZE` (default 5) | `app/db/session.py`, `app/core/config.py`, `docker-compose.yml` | New connections during 30 s of NFR-9 reads: **442 → 20** (the 20 include the harness's own). A pool of 5 beat 10 and 20 on NFR-8, NFR-9 and NFR-10, and on NFR-12's lock wait, though not on NFR-12's order p95. |
| The hot-row critical section is cut to its counters | `OrderService._reserve` | Mean `daily_inventory` lock wait: NFR-8 **1,128 → 73 ms**; NFR-12 **417 → 10 ms**. NFR-8 p95 −36 %, NFR-12 mean order time −25 %. |
| `FOR NO KEY UPDATE` on the inventory and slot rows | `OrderRepository.lock_inventory`, `lock_slot` | Needed for the change above to be deadlock-free (see below). |
| `WEB_CONCURRENCY` sets the gunicorn worker count (default 2) | `gunicorn.conf.py`, `docker-compose.yml` | 4 workers cut the server's read time about 3× on this host. The default stays 2 for now (see 3.6). |

**The critical-section change.** `_reserve` now does everything that needs no counter
*before* it locks the `daily_inventory` and `slots` rows:
- prices the order, while the Student's lock (which the subsidy rule depends on) is already held;
- inserts the order, lines, snapshot, payment, transition and idempotency result, and flushes them.

Under the counter locks, only the availability checks, the two counter updates, their
audit rows and the commit remain.

**What stays the same:**
- **Error precedence.** If the order cannot be priced as the client quoted, nothing is
  written early. The checks under the locks run as before, and the order is then priced
  again under the locks, exactly as before. A removed item is still reported as
  unavailable, and a sold-out cart is still reported as sold out, not as a price change.
- **Lock order.** It is unchanged: proposals → orders → `daily_inventory` → `slots`.

**Why the lock mode changed.** Inserting the order before the counter locks takes a
`FOR KEY SHARE` lock on its slot, through the foreign key. A later `FOR UPDATE` on that
slot would wait for every other placement's `KEY SHARE`, while those placements wait for
this one's inventory lock: a deadlock. The counters are not keys, so `FOR NO KEY UPDATE`
is enough, and it does not conflict with `KEY SHARE`. `lock_student` already worked this
way for the same reason.

**Correctness evidence.** The full backend suite passes: 923 tests, coverage 98.2 %. It
includes the 50-way concurrency tests (NFR-1, NFR-2, NFR-7), the fault injection at every
statement of every write (NFR-3), the database-down tests (NFR-16) and the ordering
acceptance tests.

### 3.4 Candidates measured, not kept

Sweep run on the reordered build, 2 workers unless stated. The values are mean
`daily_inventory` lock wait and NFR-8 p95 from a single run each.

| Config | NFR-8 lock wait | NFR-8 p95 | NFR-10 lock wait | NFR-12 lock wait |
|---|---|---|---|---|
| Base | 1,228 ms | 4,205 ms | 0.7 ms | 354 ms |
| Fixed pool 5 | **71 ms** | **2,533 ms** | 7 ms | **9 ms** |
| Fixed pool 10 | 528 ms | 4,390 ms | 14 ms | 23 ms |
| Fixed pool 20 | 1,200 ms | 5,459 ms | 45 ms | 112 ms |
| 4 workers, pool 5 | 231 ms | 3,941 ms | 7 ms | 10 ms |
| 4 workers, pool 10 | 556 ms | 2,891 ms | 0.7 ms | 39 ms |

- **Larger pools (10, 20).** On every workload but one, they gave longer lock waits and
  higher p95. More threads run database work at once, and the lock holder waits longer for
  the GIL (3.2, item 3). The exception was NFR-12's order p95, which was lower with 20
  (6,057 ms) than with 5 (7,330 ms). The fixed pool of 5 was chosen for NFR-8, the
  single-item rush that NFR-12 builds on.
- **4 workers.** The server's mean read time fell from about 950 ms to 295 ms, and the
  NFR-12 burst from about 35 s to 27 s. The client's p95 did not improve, because the load
  client competes for the same VM's CPUs. Processes × pool must stay below PostgreSQL's
  `max_connections`. A first try with 4 × 20 went past the limit of 100 and returned 503s
  ("too many clients"); with pools of 5 or 10 it ran clean.

### 3.5 Before and after

The base and final builds were measured alternately, base, final, base, final, with the
run conditions of section 1. Each cell shows the two runs, as "run 1 / run 2". All values are ms
unless marked.

| Workload | Target | Base p95 | Final p95 | Base p99 | Final p99 | Met |
|---|---|---|---|---|---|---|
| NFR-8 orders | p95 ≤ 500, p99 ≤ 1,000 | 4,559 / 3,668 | **2,509 / 2,751** | 5,015 / 4,439 | **2,788 / 2,875** | no |
| NFR-9 menu | p95 ≤ 200 | 2,060 / 1,711 | 1,946 / 1,911 | 2,647 / 2,685 | 3,138 / 2,236 | no |
| NFR-9 slots | p95 ≤ 200 | 2,086 / 1,802 | 1,993 / 1,951 | 2,789 / 2,905 | 2,969 / 2,360 | no |
| NFR-9 history | p95 ≤ 200 | 2,038 / 1,693 | 2,002 / 1,889 | 2,653 / 2,747 | 2,997 / 2,232 | no |
| NFR-9 kitchen | p95 ≤ 200 | 2,139 / 1,653 | 1,922 / 1,948 | 2,794 / 2,482 | 2,439 / 2,250 | no |
| NFR-10, 20/s for 60 s | errors < 1 % | 79 / 1,260 | 98 / 1,166 | 115 / 1,811 | 407 / 1,917 | yes: 0 errors in every run |
| NFR-11 heuristic | ≤ 5 s | 0.04 / 0.07 s | 0.04 / 0.04 s | | | yes |
| NFR-12 orders | p95 ≤ 500, p99 ≤ 1,000 | 7,645 / 9,408 | **7,481 / 6,865** | 8,180 / 11,286 | **8,091 / 7,192** | no |
| NFR-12 reads (worst of four) | p95 ≤ 200 | 4,440 / 6,380 | 4,427 / 4,748 | | | no |

| Server side (`/metrics`) | Base | Final |
|---|---|---|
| NFR-8 `daily_inventory` lock wait, mean | 1,130 / 1,125 ms | **71 / 76 ms** |
| NFR-8 `POST /orders`, mean | 2,326 / 2,226 ms | 1,932 / 1,958 ms |
| NFR-10 `daily_inventory` lock wait, mean | 0.7 / 70 ms | 0.8 / 6 ms |
| NFR-12 `daily_inventory` lock wait, mean | 279 / 555 ms | **11 / 9 ms** |
| NFR-12 `POST /orders`, mean | 6,182 / 4,957 ms | **4,385 / 3,962 ms** |
| NFR-12 200-order burst | 40.1 / 33.1 s | **30.2 / 28.3 s** |
| NFR-9 reads, mean of all four | 964 / 944 ms | 932 / 964 ms |

**Reading the numbers.**
- **The hot row is no longer the bottleneck.** Its wait fell by a factor of 15 in NFR-8 and
  40 in NFR-12. NFR-8's p95 fell by about a third, and NFR-12's mean order time by a quarter.
- **The orders stay slow** because they now queue for the pool and for the two processes'
  CPU, which (3.2, item 4) is the ceiling.
- **Reads did not change.** Ending the connection churn removed work but not that ceiling.
- **NFR-10 sits at the edge of capacity.** The same build gave a p95 of 79 ms in one run and
  1,260 ms in the next, but every run accepted all 1,200 orders without an error.
- **Errors:** across the four runs, one base-build request got no response (`ReadError`),
  and the server logged no failure for it.

### 3.6 Not done, and why

- **The conditional atomic UPDATE.** After the reorder, the inventory row is held for a
  couple of statements and the commit. NFR-8's lock wait (73 ms) is under 4 % of its order
  time (1.9 s). Merging the counter check and update into one statement would save one round
  trip of an already short wait, and cannot move the order time, which is now queueing for
  the processes.
- **Short-TTL caching of the menu and slots.** In the read profile, the menu query and
  building its rows were about a quarter of a menu request's CPU. The rest is the request
  path that every read shares: routing, dependency resolution, token check and user load,
  and serialisation. A cache could therefore save at most about a quarter of the menu's
  cost, at the price of showing stale portion counts during a rush. The server would still
  refuse a sold-out order, but the menu would claim it was available.
- **More worker processes by default.** This depends on the host's CPUs, and the free-tier
  EC2 instance has two. The setting is now an environment variable. The deployment uses 2
  workers, one per CPU (§4), but this was not measured there.

### 3.7 Where this leaves NFR-8, NFR-9 and NFR-12

Under the strict reading the harness uses, they are not met on this laptop. That reading
is 50 or 100 clients, each sending its next request as soon as the last one returns. To
meet NFR-9 under it, the stack would have to answer about 500 reads/s; it answers about
100/s.

**The limit.** The Python work per request across two processes, not the database and
not, any longer, lock contention.

**Options:**
1. **Find the rest of the per-request CPU.** The next step is profiling the shared request
   path: dependencies, the user load, serialisation.
2. **Give `caf-api` more CPU.** More worker processes on a larger host, measured on AWS.
3. **Pin down "concurrent users" with the team.** NFR-9 and US-31 AC2 do not define think
   time, and 100 users who each pause between pages send far fewer requests per second than
   100 users who never pause. This is a requirements decision for the team, recorded here so
   that the harness's reading stays explicit. It is not a change made to pass the test.

## 4. Run 2: AWS (EC2 + RDS)

**Not run for Deliverable 3.** The stack was deployed on 5 Nov 2026 (CAFIITK-190, PR #106):
EC2 `t3.small` (2 vCPU) and RDS `db.t4g.micro`, behind CloudFront. No load run was made
against it before the deadline. None of the three planned steps was done:

- **The harness against the deployed stack, with the load client off the instance.** Not
  run. If it is run later, `--fresh` must not be used, since it empties the database.
- **An LLM agent run timed with the key configured.** Not possible: no `CAF_LLM_API_KEY`
  is set on the deployment, so it runs the heuristic planner only (`Cost-Report.md` §5).
- **`WEB_CONCURRENCY` and `CAF_DB_POOL_SIZE` tuned for the instance.** The deployment runs
  with `WEB_CONCURRENCY=2` (one worker per vCPU) and `CAF_DB_POOL_SIZE=5`
  (`deploy/.env.production.example`). These follow §3 but were not measured on AWS.

So no performance result in this report comes from AWS. The laptop results stand as the
record: NFR-8, NFR-9 and NFR-12 are not met (§3.7, §5.4); NFR-10 is met on the local stack
(§2). The Jira tasks for NFR-8, 9 and 12 were closed by team decision, with these shortfalls
recorded on each; NFR-10's was closed on the local result. How to run the AWS measurement is described on CAFIITK-190
and in §5.4.

## 5. US-31 acceptance (CAFIITK-156)

US-31 ("Ordering stays fast at peak") is accepted against NFR-8, NFR-9 and NFR-12. Its two
criteria are named tests in `backend/tests/test_us31_peak.py`. They run the workloads above
at full scale and assert the targets. They need a running stack, so they are skipped unless
`CAF_PERF_BASE_URL` and `CAF_PERF_DATABASE_URL` are set; `tests/test_perf.py` keeps the
harness itself tested in CI at 5 % scale.

| Test | Criterion | Workloads it runs |
|---|---|---|
| `test_tc_us31_ac1_order_creation_p95_and_p99_with_50_clients` | AC1: 50 concurrent clients create orders for one item and slot; p95 ≤ 500 ms, p99 ≤ 1 s | NFR-8, and the order burst of NFR-12 |
| `test_tc_us31_ac2_reads_p95_with_100_users` | AC2: 100 concurrent users read the menu, slots, history and queue; p95 ≤ 200 ms | NFR-9 |

### 5.1 Run: Docker Compose on an Apple M2 (4 Nov 2026)

**Environment.**
- Commit: `82ef554` (`develop`, after CAFIITK-188), before any CAFIITK-189 change.
- Host: Apple M2 (8 cores) with 8 GB RAM, macOS. Docker 29.5 with 4 CPUs and 5.8 GB.
- Stack: the same Compose stack as Run 1, with `caf-api` under gunicorn with 2 Uvicorn workers.
- mockpay approves with no delay. The load generator ran on the same machine as the stack.

**Command** (from `backend/`):

```bash
CAF_JWT_SECRET=<the stack's secret> \
CAF_PERF_BASE_URL=http://localhost:8000 CAF_PERF_MOCKPAY_URL=http://localhost:8001 \
CAF_PERF_DATABASE_URL=postgresql+psycopg://caf:<password>@localhost:5432/caf \
    .venv/bin/pytest tests/test_us31_peak.py -s
```

**Results (client side).** Both tests failed.

| Criterion | Workload | Requests | p50 ms | p95 ms | p99 ms | Errors | Met |
|---|---|---|---|---|---|---|---|
| AC1 | NFR-8: 50 clients, 200 orders, one item and slot | 200 | 389 | 737 | 847 | 0 | **no** (p95) |
| AC1 | NFR-12 orders: 200 by 50 clients, 100 readers alongside | 200 | 708 | 1037 | 1333 | 0 | **no**; burst 4.9 s, within 60 s |
| AC2 | NFR-9 menu, 100 readers for 30 s | 1588 | 275 | 1795 | 2271 | 0 | **no** |
| AC2 | NFR-9 slots | 1537 | 272 | 1846 | 2308 | 0 | **no** |
| AC2 | NFR-9 order history | 1512 | 270 | 1762 | 2283 | 0 | **no** |
| AC2 | NFR-9 kitchen queue | 1540 | 290 | 1777 | 2466 | 0 | **no** |

The reads measured during NFR-12 also missed their target, with p95 1035–1397 ms.

**Server side (from /metrics).**

| Workload | Route or lock | Count | Server mean ms | Server p95 (bucket) |
|---|---|---|---|---|
| NFR-8 | `POST /api/v1/orders` | 200 | 390 | ≤ 750 |
| NFR-8 | lock wait: `daily_inventory` | 200 | 190 | ≤ 500 |
| NFR-9 | `GET /api/v1/menu`, `/slots`, `/orders`, `/kitchen/queue` | 1512–1588 each | 57–67 | ≤ 250 |
| NFR-12 | `POST /api/v1/orders` | 200 | 630 | ≤ 2500 |

### 5.2 What this run adds

1. **Every request succeeded.** All 7,811 measured requests were answered, with no errors.
   The system stays correct at peak; the gap is latency only. This agrees with Run 1.
2. **AC1 is close.** On this machine NFR-8's p99 (847 ms) meets its target and p95 misses by
   237 ms. The server's own mean for an order is 390 ms, about half of it spent waiting for
   the single `daily_inventory` row (190 ms). That was the hot-row queue analysed in §3.2.
3. **AC2's time is spent before the application.** During NFR-9 the server measured each read
   at about 60 ms on average, with every bucket p95 ≤ 250 ms. The client saw p50 ≈ 270 ms
   and p95 ≈ 1.8 s. Most of each read's latency therefore lies between the client and the
   application:
   - the gunicorn and Uvicorn accept queue;
   - the TCP connections;
   - or the load generator itself, one Python process driving 100 users on the same 8 GB
     machine as the stack.

   This agrees with §3.2 and §3.7. For CAFIITK-189, it points at worker count and at running
   the load generator on another machine before any query is tuned.

### 5.3 Re-run after CAFIITK-189

The tests were run again on the same machine with the same settings (2 workers, pool of 5),
at commit `40f658f`. That is `develop` with CAFIITK-189's changes, merged into this branch.
Both tests failed again.

| Criterion | Workload | Before 189: p95 / p99 ms | After 189: p95 / p99 ms | Errors after | Met |
|---|---|---|---|---|---|
| AC1 | NFR-8 orders | 737 / 847 | **570 / 615** | 0 | **no** (p95, by 70 ms) |
| AC1 | NFR-12 orders | 1037 / 1333 | 1803 / 2047 (burst 8.2 s) | 0 | **no** |
| AC2 | NFR-9 menu | 1795 / 2271 | 1078 / 2110 | **1** | **no** |
| AC2 | NFR-9 slots | 1846 / 2308 | 1108 / 2077 | 0 | **no** |
| AC2 | NFR-9 order history | 1762 / 2283 | 1075 / 2198 | 0 | **no** |
| AC2 | NFR-9 kitchen queue | 1777 / 2466 | 1234 / 2173 | 0 | **no** |

| Server side (`/metrics`) | Before 189 | After 189 |
|---|---|---|
| NFR-8 `daily_inventory` lock wait, mean | 190 ms | **15 ms** |
| NFR-8 `POST /orders`, mean | 390 ms | 355 ms |
| NFR-9 reads, mean of the four | 57–67 ms | 462–516 ms |

**Reading the numbers.**
- **The hot-row lock is solved.** Its wait fell from 190 ms to 15 ms, which agrees with
  §3.5. NFR-8 is now 70 ms from its p95 target and meets its p99 target.
- **Reads improved for the client** (p95 from about 1.8 s to about 1.1 s), but the server
  now counts about 460 ms per read where it counted about 60 ms. The time moved inside the
  measured window rather than disappearing. This fits requests now waiting for one of the
  smaller pool's connections inside `caf-api` (§3.3), and the limit of §3.7: CPU across two
  processes.
- **The NFR-12 orders were slower** than before 189 in this single run. §3.5 shows how much
  one run can vary on a laptop, so one run on each side cannot show a regression. The AWS
  run that would have settled it was not done (§4).
- **One read got no response.** A menu read ended in a `RemoteProtocolError` (the
  connection closed without an answer), the first error in either of this section's runs.
  §3.5 reports a similar `ReadError` on the base build. Under peak read load, a connection
  can be dropped. This should be investigated, and raised as a Bug if it repeats.

### 5.4 Status of US-31

**Not met** on the local stack before or after CAFIITK-189: AC1 and AC2 both fail. AC1 is
close (NFR-8 p95 570 ms against 500 ms). AC2 is about five times over its target.
CAFIITK-156 delivers the acceptance tests and these two measurements.

The criteria were to be measured again on AWS with the same command, with the load
generator off the instance. That run was not done for D3 (§4), so US-31 stays not met.
CAFIITK-190 records the command for a later run. Whether NFR-9's "100 concurrent users" includes think time
(§3.7, option 3) changes AC2's load, and is for the team to decide.
