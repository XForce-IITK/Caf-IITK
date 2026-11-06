# Deployment Documentation

Caf@IITK, Deliverable 3. This document describes the environments, the build and release pipeline, the AWS deployment and how it was verified. The step-by-step runbook, with every console setting and command, is [`deploy/README.md`](../deploy/README.md). Costs are in `Cost-Report.md`.

## 1. Environments

| Environment | Where | Purpose |
|---|---|---|
| Local | Docker Compose on a developer machine (`docker-compose.yml`) | Development, manual testing, the performance runs in `Performance-Report.md` |
| CI | GitHub Actions (`.github/workflows/ci.yml`) | Every PR and every push to `develop` and `main` |
| Production | AWS `ap-southeast-2` (Sydney): EC2 + RDS behind CloudFront (`docker-compose.prod.yml`) | The deployed system, used for the demo |

**Live URL:** https://dh3nmzc5y7ht8.cloudfront.net (the Flutter web client and the API on the same origin).

The Android app is built from the same Flutter codebase (`flutter build apk --release --dart-define=API_BASE_URL=https://<deployed host>`; see the root `README.md`). It is sideloaded, signed with the debug key, and not published to a store.

## 2. Architecture of the deployment

```
browser / Android ──HTTPS──▶ CloudFront ──HTTP, port 80──▶ EC2 t3.small ─────────────────────────────┐
                              (*.cloudfront.net            nginx: serves the web build, proxies /api │
                               certificate, HSTS)            ├─▶ caf-api (gunicorn, 2 workers, 127.0.0.1:8000)
                                                             ├─  caf-worker (advisory-lock leader)    │
                                                             └─  mockpay (internal only)              │
                                                                         │                             │
                                                                         ▼                             │
                                                             RDS db.t4g.micro, PostgreSQL 16, Single-AZ, not public
```

| Component | Resource | Notes |
|---|---|---|
| CDN and TLS | CloudFront, `*.cloudfront.net` certificate | Redirects HTTP to HTTPS; caching disabled; forwards `Authorization` |
| Compute | EC2 `t3.small` (2 vCPU), Ubuntu 24.04, Elastic IP | Runs four containers from `docker-compose.prod.yml` |
| Database | RDS PostgreSQL 16, `db.t4g.micro`, 20 GiB gp3, Single-AZ | Reachable only from the EC2 security group; connections over SSL |
| Network | Security groups `caf-ec2-sg`, `caf-rds-sg` | Port 80 admits only CloudFront's origin-facing prefix list; SSH only from one address; 8000 and 8001 never opened |

### Why CloudFront instead of Let's Encrypt

The campus network resolves the free dynamic-DNS names (sslip.io, nip.io, traefik.me, DuckDNS) to a block page, and Let's Encrypt will not issue for `amazonaws.com` names. CloudFront's own name has a valid certificate, is free, and resolves on campus. The cost is that TLS ends at CloudFront (`Security-Threat-Model.md` R1).

## 3. Same images and migrations everywhere (NFR-40)

- **One backend image.** `docker-compose.prod.yml` builds `./backend` once, tags it `caf-backend`, and runs `migrate`, `caf-api`, `caf-worker` and `mockpay` from it. The local `docker-compose.yml` uses the same Dockerfile.
- **One migration chain.** Alembic `0001` to `0007` ran unchanged on RDS. Migration 0007 grants `caf_agent` to the database login user, which RDS needs because its login user is not a superuser. It is in the shared chain, so local and AWS stay the same. `tests/test_managed_database_roles.py` reproduces the RDS situation: a non-superuser login with CREATEROLE.
- **Only configuration differs.** Production sets `CAF_ENV=production`, which turns off mockpay's test controls and restricts CORS to the client origin.

## 4. Configuration

Settings come from `CAF_*` environment variables (`backend/app/core/config.py`). On the instance they are in `.env`, created from `deploy/.env.production.example`, readable only by its owner (`chmod 600`), and never committed (NFR-24).

| Variable | Purpose |
|---|---|
| `CAF_HOST` | The CloudFront domain: the client origin and the only CORS origin |
| `CAF_DATABASE_URL` | RDS connection |
| `CAF_JWT_SECRET` | Token signing key, at least 32 bytes; production refuses a default or short one |
| `WEB_CONCURRENCY`, `CAF_DB_POOL_SIZE` | caf-api worker processes (2) and fixed connections per process (5); well under the RDS connection limit |
| `CAF_SEED_ADMIN_*`, `CAF_SEED_KITCHEN_*` | The first Administrator and Kitchen accounts, seeded on first start (FR-2) |
| `CAF_LLM_API_KEY`, `CAF_LLM_MODEL` | The agent's LLM. **Empty on the deployment**, so the agent uses the heuristic planner (FR-59) |

Parameters an Administrator can change at run time (SRS Table 4.0-B) are in the `settings` table, not in environment variables.

## 5. Build and release pipeline

**Branching:** `CAFIITK-<issue>-<slug>` branches off `develop`. Every change merges by PR into `develop`, with one approval from someone other than the author. `develop` merges into `main` once per sprint, by a release PR with a merge commit (not a squash), and `main` is tagged.

**Required CI checks** (repository ruleset; strict up-to-date rule):

| Check | What it does |
|---|---|
| Jira key in branch and PR title | The branch name, the PR title and every commit message in the PR must carry a `CAFIITK-<n>` key (NFR-44) |
| Backend lint, type-check and tests | ruff, ruff format, mypy (strict); pytest against PostgreSQL 16 in testcontainers, with an 80% coverage gate |
| Client analyze, tests and web build | Checks that the generated API client matches the OpenAPI schema (NFR-39); `flutter analyze`; `flutter test` with an 80% coverage gate (generated code not counted); `flutter build web` |
| Secret scan (gitleaks) | Scans the full git history on every run |

**Releases:**

| Release | PR | Tag | Date |
|---|---|---|---|
| Sprint 1 | #26 | — | 6 Oct 2026 |
| Sprint 2 / Deliverable 2 | #63 | `d2` | 15 Oct 2026 |
| Sprint 3 / Deliverable 3 | #109 | `d3` | 6 Nov 2026 |

**Deploying a release** is manual: `git pull` on the instance, then `docker compose -f docker-compose.prod.yml up -d --build`. `migrate` runs `alembic upgrade head` before `caf-api` starts. The Flutter web build is made on a laptop and copied over with `rsync`, because the instance is too small to build Flutter (runbook §6–7). No CD pipeline deploys automatically.

## 6. Health and monitoring

- `/health` (liveness) and `/ready` (database reachable, else 503) back the Docker health checks (NFR-31).
- `/metrics` (Prometheus format) is served only on the instance, through an SSH tunnel; it answers 404 from outside.
- Logs are JSON with a correlation ID on every line; passwords, tokens and keys are removed by a log filter (NFR-28 to NFR-30). They are read with `docker compose logs`.
- The containers restart on their own after a crash or a reboot.

## 7. Verification of the deployment

Checked from the campus network on 6 Nov 2026 (CAFIITK-107, CAFIITK-120, PR #107). Every request was unauthenticated:

| Check | Result |
|---|---|
| `http://…/ready` | 301 to HTTPS |
| TLS | `CN=*.cloudfront.net`, issuer Amazon RSA 2048 M04, verification OK; HSTS `max-age=31536000` |
| `/health`, `/ready` | `{"status":"ok"}`, `{"status":"ready"}` |
| `/metrics` from outside | 404 |
| Client `/`, `/login`, `/student/orders` (deep link) | 200 |
| CORS preflight from the client origin | 200, `access-control-allow-origin` set to that origin |
| CORS preflight from `https://evil.example` | 400 |
| Elastic IP on ports 80 and 8000 | Not reachable |

Further checks from the deployment PR (#106), run by its author:
- **Accounts and the menu:** register, login, `GET /auth/me` and `GET /menu` with a Bearer token through CloudFront.
- **Client IP for the login rate limit:** a failed login with a spoofed `X-Forwarded-For` was audited with the real client IP.
- **Database roles on RDS:** the login user is a member of `caf_app` and `caf_agent`; `caf_app` has no UPDATE or DELETE on `audit_log`; `caf_agent` can read the `agent_*` views and is refused `users`.
- **Browser check as the Administrator:** added an item and ran the agent (heuristic fallback).

## 8. Known limitations

- **TLS ends at CloudFront.** The hop from CloudFront to the instance is plain HTTP, limited to CloudFront's address list.
- **Single points of failure.** One EC2 instance and a Single-AZ database, with no failover; the free tier rules out more.
- **No automatic deployment.** Deploys are manual, and nothing ties the running version to a tag. Check with `git log -1` on the instance.
- **No load test on AWS** (`Performance-Report.md` §4).
- **No LLM key on the deployment**, so the agent runs on the heuristic planner only.

## 9. Teardown

After the demo, disable and delete the CloudFront distribution, terminate the EC2 instance, release the Elastic IP, and delete the RDS database without a final snapshot (runbook, "After the demo"). The account is on the AWS Free plan and cannot be charged in any case (`Cost-Report.md`).
