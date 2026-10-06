# Caf@IITK

Campus cafeteria pre-order and pickup-slot platform (CS455, IIT Kanpur, Team XForce).
Requirements and design: `Documentation/` (SRS v2.0 and SADD).

| Path | What |
|---|---|
| `backend/` | Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL 16. One codebase for `caf-api` and `mockpay` (and later `caf-worker`). |
| `app/` | Flutter Web client (Riverpod, GoRouter, Dio). |
| `docker-compose.yml` | Local stack: PostgreSQL 16, migrations, `caf-api` on :8000, `mockpay` on :8001. |

## Prerequisites

- Docker (Docker Desktop, or Colima on macOS: `brew install colima docker docker-compose && colima start`)
- Python 3.12
- Flutter SDK (only for work on `app/`)

## Run the stack

```sh
cp .env.example .env          # then set CAF_JWT_SECRET
docker compose up --build
curl localhost:8000/health    # {"status":"ok"}
```

API docs: http://localhost:8000/docs

## Backend development

```sh
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'

.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy app tests
.venv/bin/pytest --cov          # needs Docker running; 80% coverage gate
```

Tests start a real PostgreSQL 16 container with testcontainers and migrate it
to head, so Docker must be running. On Colima, `tests/conftest.py` finds the
socket automatically.

### Where code goes

Each area has its own package under `backend/app/modules/` (`identity`,
`catalogue`, `inventory`, `slots`, `pricing`, `ordering`, `payments`, `audit`).
Add endpoints to that module's `router.py`; it is already mounted under
`/api/v1`. Layering: `router.py` → `service.py` → domain logic →
`repository.py` → PostgreSQL. Services own transactions; only repositories
issue SQL.

The full core schema (SADD Figure 2.5) is already in migration `0001`. If a
change needs a new column or table, add a new migration on top of the latest
one (`alembic revision --autogenerate -m "..."`) and rebase on `develop` before
merging so the migration history stays linear.

### Payments

Services call the payment provider only through `PaymentGateway`
(`app/modules/payments/gateway.py`). Take it with
`Depends(get_payment_gateway)`; it raises if the request's session still has a
transaction open (NFR-6), so commit before calling it. Tests that do not need
real HTTP can use `FakePaymentGateway`.

`mockpay` approves every authorisation by default. To demonstrate a failure,
set the outcome (not available when `CAF_ENV=production`):

```sh
curl -X PUT localhost:8001/_control/outcome -H 'content-type: application/json' \
  -d '{"mode": "decline"}'      # or "timeout", or {"mode": "approve", "delay_ms": 3000}
```

## Client development

```sh
cd app
flutter pub get
flutter analyze && flutter test
flutter run -d chrome          # talks to caf-api on http://localhost:8000
```

Point the client at another API with
`--dart-define=API_BASE_URL=https://...`. In development caf-api accepts
browser calls from any localhost port; in production set `CAF_CORS_ORIGINS` to
the client's origin (NFR-27).

### Login, routing and networking

- `lib/auth/session.dart` holds the session (`sessionProvider`). Tokens are kept
  in memory only, so reloading the page logs the user out.
- `lib/router.dart` sends a logged-in user to exactly one dashboard by role
  (`/student`, `/kitchen`, `/admin`) and everyone else to `/login` (FR-5). Add
  a role's screens as child routes under its dashboard path.
- Every call made through `apiProvider` gets the access token (refreshed once
  on a 401) and a fresh `X-Request-ID`.
- For create, modify and cancel, make one key with `newIdempotencyKey()` when
  the user confirms and pass it to the call. Such requests are retried up to 3
  times with back-off on a network failure or a 502/503/504, reusing the key
  (NFR-18).
- Show failures with `describeApiError(error)` from `lib/api/errors.dart`.

### Student flow

`lib/student/` is the Student dashboard: menu with portions left, slot picker
with seats left, the full price breakdown before confirming (NFR-32), and
placing the order. `student_state.dart` holds the cart and the checkout steps;
a new idempotency key is made for each priced quote and reused if that
confirmation is repeated. Modify, cancel and order tracking are added once
their endpoints exist.

### API client

`app/lib/api/generated/` is generated from caf-api's OpenAPI schema
(`app/openapi.json`) and is never edited by hand. After any change to an
endpoint or a request/response schema, regenerate it and commit the result in
the same PR; CI regenerates it and fails if the committed files differ (NFR-39).

```sh
app/tool/generate_api.sh      # needs the backend venv and Flutter
```

Use the client through `apiProvider` in `app/lib/api/api.dart`, for example
`ref.read(apiProvider).catalogue.browseMenu(date: serviceDate(DateTime.now()))`.
Methods are named after the backend endpoint functions, so keep those names
unique. Pass service dates through `serviceDate(...)`: the backend rejects a
date that carries a time of day.

## Workflow

Branch `CAFIITK-<issue>-<slug>` off `develop`; start every commit message and
PR title with `CAFIITK-<issue>: `; open a PR into `develop` with test evidence
and get it reviewed by someone other than the author.
