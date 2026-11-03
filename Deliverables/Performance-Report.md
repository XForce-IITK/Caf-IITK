# Caf@IITK Performance Report

CAFIITK-188. Latency, throughput and agent run time against NFR-8 to NFR-12 (SRS §4).
These are the baseline ("before") numbers for the bottleneck analysis in CAFIITK-189.
The numbers of record for Deliverable 3 come from the AWS deployment (CAFIITK-190) and
will be added as a second run in this report; the laptop run below stays as the baseline.

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

## 2. Run 1: Docker Compose on a laptop (baseline)

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
environment. The heuristic fallback (FR-59) was timed instead. The LLM run is to be
measured on AWS, where the key is set.

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

## 3. Observations for CAFIITK-189

These are what the baseline shows. The analysis and any changes belong to CAFIITK-189.

1. **`caf-api` is CPU-bound.** During a short repeat of the NFR-9 read load (15 s),
   `docker stats` showed the `api` container at about 240 % CPU. That is two gunicorn
   processes, each close to one core under the Python GIL. PostgreSQL was at 17–40 %. The
   VM has 12 CPUs, so the cap comes from the two processes, not from the machine.
2. **Even a request that does almost nothing is slow.** `GET /ready` runs a single
   `SELECT 1` with no locks, yet it took about 1 s during the read load. A request that
   arrives waits for a thread and the GIL before it runs any SQL.
3. **Connections are held while Python works.** During the same burst, 22 of 38 database
   sessions were `idle in transaction`: they held a pool connection while the process did
   CPU work such as serialisation. A slow process therefore also holds its connections longer.
4. **The single hot row serialises NFR-8.** All 200 orders lock the same `daily_inventory`
   row, and the mean wait for that lock was 1.0 s. The lock order (SADD) makes this a queue
   by design. Its length depends on how long each holder's transaction runs, which (1)
   stretches. The `slots`, `orders` and `users` locks are cheap (2–4 ms). With NFR-10's load
   spread over three items, the inventory lock wait drops to 345 ms.
5. **There were no errors anywhere.** All 5,941 measured requests were answered, with no
   5xx, timeouts or 503s. The system stays correct under load; it is too slow.

Candidates for CAFIITK-189, to be measured again with this harness:
- More `caf-api` worker processes (the free-tier EC2 instance has fewer CPUs, so this must be measured there as well).
- Less per-request Python work on the hot paths: serialisation, and repeated settings reads.
- A shorter `daily_inventory` lock hold in the reserve transaction.
- Fewer statements per order.

**Caveat:** the load generator ran on the same laptop and took CPU from the stack, so these
numbers are pessimistic. The AWS run (section 4) will separate the load generator from
the server.

## 4. Run 2: AWS (EC2 + RDS)

Pending CAFIITK-190. The same command will be run against the deployed stack, with the load
generator off the instance, and an LLM agent run timed with the key configured.

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
   the single `daily_inventory` row (190 ms). That is the hot-row queue named in §3 (4).
3. **AC2's time is spent before the application.** During NFR-9 the server measured each read
   at about 60 ms on average, with every bucket p95 ≤ 250 ms. The client saw p50 ≈ 270 ms
   and p95 ≈ 1.8 s. Most of each read's latency therefore lies between the client and the
   application:
   - the gunicorn and Uvicorn accept queue;
   - the TCP connections;
   - or the load generator itself, one Python process driving 100 users on the same 8 GB
     machine as the stack.

   This agrees with §3 (1)–(2). For CAFIITK-189, it points at worker count and at running
   the load generator on another machine before any query is tuned.

### 5.3 Status of US-31

**Not met** on the local stack: AC1 and AC2 both fail. CAFIITK-156 delivers the acceptance
tests and this measurement. The criteria should be measured again with the same command:
- after CAFIITK-189's changes;
- and on AWS (CAFIITK-190), with the load generator off the instance.

US-31 can be closed only when both tests pass there.
