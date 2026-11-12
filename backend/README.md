# VibeWealth Backend

The backend is a modular FastAPI application using SQLAlchemy 2.x and local
PostgreSQL. It includes models and Alembic migrations for users, accounts,
categories, transactions, budgets, savings goals and entries, assistant
conversations and messages, and authentication sessions. It provides health
endpoints and cookie-based registration, login, current-user, CSRF-token, and
logout endpoints. Authentication uses Argon2id password hashes and
PostgreSQL-backed opaque sessions. Transaction editing/import APIs, a
persistent assistant service, and live AI integration are not implemented.
Schema changes are managed explicitly with Alembic.

This backend is not a declaration of public launch readiness. Account recovery,
production deployment configuration, and a broader security review remain
separate work.

## Requirements

- Python 3.12
- pip
- Docker Engine and Docker Compose (the project's configured database setup uses WSL2 Ubuntu)

## Set up a Python environment

From the repository root in WSL2 Ubuntu:

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
```

Do not use a Windows `.venv` from WSL. Install dependencies:

```sh
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Configure environment variables

Create `.env` from `.env.example` once and set a private `POSTGRES_PASSWORD`.
The example password is a placeholder and must not be used as a credential.
`DATABASE_URL` is optional; when blank, the backend builds a PostgreSQL URL
from the `POSTGRES_*` settings. A supplied URL must use the
`postgresql+psycopg` driver.

From `backend/`, create the file without overwriting an existing local
configuration, then edit the placeholder password:

```sh
test -f .env || cp .env.example .env
```

| Variable | Default | Description |
| --- | --- | --- |
| `POSTGRES_DB` | `vibewealth` | Local PostgreSQL database name |
| `POSTGRES_USER` | `vibewealth_app` | Local PostgreSQL user |
| `POSTGRES_PASSWORD` | *(set locally)* | Local PostgreSQL password |
| `POSTGRES_HOST` | `localhost` | PostgreSQL host used by the backend |
| `POSTGRES_PORT` | `5432` | Host loopback port mapped to PostgreSQL |
| `DATABASE_URL` | *(optional)* | Full `postgresql+psycopg` override; leave blank to construct the URL from `POSTGRES_*` settings |
| `APP_TITLE` | `VibeWealth API` | FastAPI application title |
| `APP_VERSION` | `0.1.0` | API version |
| `APP_ENVIRONMENT` | *(required)* | Explicitly select `development`, `test`, or `production`; missing or unsupported values fail startup |
| `ALLOWED_FRONTEND_ORIGINS` | `["http://localhost:5173"]` | JSON list of exact allowed frontend origins; wildcards are rejected |
| `ALLOW_INSECURE_COOKIES` | `false` | Must be explicitly `true` in development to use HTTP cookies locally |
| `CSRF_SIGNING_SECRET` | *(development-only fallback)* | Production requires a unique secret of at least 32 characters; generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `AUTH_LOGIN_IP_LIMIT` | `30` | Login attempts allowed per client IP in the login window |
| `AUTH_LOGIN_IDENTITY_LIMIT` | `5` | Login attempts allowed per client IP and normalized email in the login window |
| `AUTH_LOGIN_WINDOW_SECONDS` | `60` | Login token-bucket refill window, from 1 to 86400 seconds |
| `AUTH_REGISTRATION_IP_LIMIT` | `5` | Registration attempts allowed per client IP in the registration window |
| `AUTH_REGISTRATION_IDENTITY_LIMIT` | `2` | Registration attempts allowed per client IP and normalized email in the registration window |
| `AUTH_REGISTRATION_WINDOW_SECONDS` | `900` | Registration token-bucket refill window, from 1 to 86400 seconds |

`.env` and other local secret files are excluded from Git. Do not commit local
credentials.

Set `APP_ENVIRONMENT` explicitly. The checked-in example selects
`development`; missing, empty, or unsupported values fail configuration. For
local Vite development, keep the exact origin `http://localhost:5173` and set
`ALLOW_INSECURE_COOKIES=true` in the private `.env`. This is accepted only in
`development`; all other environments issue Secure cookies. Production must set
`APP_ENVIRONMENT=production`, use HTTPS for every explicitly listed frontend
origin, and provide a unique `CSRF_SIGNING_SECRET`. HTTP production origins,
including localhost, are rejected. Production cookies use a host-only
`__Host-vibewealth_session` name, `Secure`, `HttpOnly`, `SameSite=Lax`, and
`Path=/`, with no `Domain` attribute. Startup rejects missing production
origins or CSRF key material.

When constructing an app with `create_app(settings=...)`, the supplied
settings must use the same SQLAlchemy URL as the shared database engine. A
mismatch raises a configuration error instead of silently applying security
settings to an app connected to a different database.

The checked-in `.env.example` lists the database, application, cookie/CSRF, and
rate-limit settings consumed by `Settings` and Docker Compose. The optional
`POSTGRES_TEST_DATABASE_URL` is test-only and intentionally is not an
application setting; its safe use is described under testing.

## Run the API

From `backend/` with the environment active:

```sh
uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`. `GET /health` checks the API
process; `GET /health/db` runs `SELECT 1` and returns 503 if PostgreSQL is not
reachable. Current endpoints are:

| Method | Path | Behavior |
| --- | --- | --- |
| `GET` | `/health` | Process health; does not query PostgreSQL |
| `GET` | `/health/db` | Executes `SELECT 1` and reports database availability |
| `POST` | `/api/auth/register` | Creates a user, default account, default categories, and session |
| `POST` | `/api/auth/login` | Verifies credentials and creates an independent session |
| `GET` | `/api/auth/me` | Returns the authenticated user projection |
| `GET` | `/api/auth/csrf` | Returns a session-bound CSRF token |
| `POST` | `/api/auth/logout` | Revokes the current session and clears its cookie |
| `GET` | `/api/accounts` | Lists the user's active accounts and current balances |
| `GET` | `/api/accounts/{account_id}` | Retrieves one owned account and its current balance |
| `GET` | `/api/accounts/{account_id}/balance?as_of=YYYY-MM-DD` | Calculates a current or historical balance; `as_of` is optional |
| `PATCH` | `/api/accounts/{account_id}` | Updates account name/type and, before the first transaction, opening balance/date |
| `GET` | `/api/categories` | Lists the authenticated user's active categories for selection |
| `POST` | `/api/transactions` | Creates an income or expense transaction; requires CSRF protection |
| `GET` | `/api/transactions` | Lists live transactions with filters and pagination |
| `GET` | `/api/transactions/{transaction_id}` | Retrieves one owned live transaction |
| `GET` | `/api/budgets?month_start=YYYY-MM-01` | Lists owned budgets and actual spending; month filter is optional |
| `GET` | `/api/budgets/{budget_id}` | Retrieves one owned budget and its actual spending |
| `POST` | `/api/budgets` | Creates an overall or active expense-category budget; requires CSRF protection |
| `PATCH` | `/api/budgets/{budget_id}` | Updates an owned budget; requires CSRF protection |
| `DELETE` | `/api/budgets/{budget_id}` | Deletes an owned budget; requires CSRF protection |
| `GET` | `/api/goals?offset=0&limit=50` | Lists active owned savings goals and allocation summaries |
| `GET` | `/api/goals/{goal_id}` | Retrieves one active owned goal and per-account allocations |
| `POST` | `/api/goals` | Creates a goal; requires CSRF protection |
| `PATCH` | `/api/goals/{goal_id}` | Updates permitted goal metadata; requires CSRF protection |
| `DELETE` | `/api/goals/{goal_id}` | Releases allocations and soft-deletes the goal; requires CSRF protection |
| `GET` | `/api/goals/{goal_id}/entries?offset=0&limit=50` | Lists append-only goal ledger history |
| `POST` | `/api/goals/{goal_id}/contributions` | Allocates available account money to a goal; requires CSRF protection |
| `POST` | `/api/goals/{goal_id}/withdrawals` | Releases an allocation from the same goal/account pair; requires CSRF protection |

Account and transaction reads require a valid session. Category reads also
require a valid session; category listing excludes archived categories and
other users' categories. Account updates and transaction creation also require
the trusted Origin and session-bound CSRF header. Account
creation/deletion and transaction editing/deletion endpoints are not exposed.
Registration remains the only account-creation path and
creates one default cash, bank, or wallet account with a zero opening balance.

## Account balances and transaction rules

`opening_balance_paise` is the account's starting balance at the beginning of
`opening_balance_as_of`. Transactions dated that day are added to it. A current
or historical balance is the opening balance plus non-deleted income minus
non-deleted expenses dated from the opening date through the requested date.
Historical balance requests before the opening date or after today are
rejected. Amounts and calculations stay in integer paise; transaction inputs
must be positive integers within JavaScript's safe-integer range. Every daily
closing balance must also remain in that range. A backdated transaction is
rejected if it would make any affected daily closing balance unsafe, even when
the current balance would remain safe.

Transaction creation requires an account and category owned by the authenticated
user. The category must be active and its type must match the transaction type.
Archived categories remain visible by name on historical transactions but are
rejected for new transactions. Dates cannot be in the future or before the
account opening date. Deleted transactions are omitted from history and every
balance calculation.

Account name and asset type (`cash`, `bank`, or `wallet`) can be changed. The
opening balance and date may be changed only before any transaction has ever
been created for the account; soft-deleting a transaction does not unlock them.
Account updates and transaction creation acquire the account row lock first, so
concurrent writes serialize around that invariant. Services stage database
changes without committing; the HTTP request owns commit and rollback.

Account responses include the actual `balance_paise`, net
`goal_allocated_paise`, and `available_to_spend_paise`. The actual balance is
opening balance plus live income minus live expenses; goal entries never change
it. Available-to-spend is actual account balance minus the net allocations in
that account. Historical balance responses include allocations effective on or
before the requested India-calendar date.

Transaction listing supports `account_id`, `transaction_type`, `category_id`,
`date_from`, `date_to`, `offset`, and `limit` query parameters. Results exclude
soft-deleted rows and sort by transaction date, creation time, and UUID in
descending order. `offset` defaults to 0; `limit` defaults to 50 and is capped
at 100.

Registration creates the user, their one default asset account, seeded
categories, and initial session in one database transaction. That account starts
with a zero opening balance dated yesterday in `Asia/Kolkata`. Login errors are
generic for unknown users and incorrect passwords. Both issue an `HttpOnly`,
`SameSite=Lax` cookie; production additionally requires `Secure` and uses the
host-only `__Host-` cookie name. The session token contains 256 bits of random
data; only its SHA-256 digest is stored in PostgreSQL. Sessions expire after 12
hours idle or 30 days absolute, whichever comes first. Logout revokes only the
current session; it does not delete other sessions.

Passwords must contain at least 15 Unicode code points. They are not trimmed or
normalized and no composition rules are imposed. Passwords are hashed with
Argon2id (time cost 3, memory cost 65536 KiB, parallelism 4); plaintext
passwords are not stored.

Registration and login require an exact configured `Origin`. If `Origin` is
absent, a `Referer` whose parsed origin exactly matches the allowlist is
accepted. If both are absent, or either supplied origin is malformed or
untrusted, the request is rejected. This policy also applies to non-browser
clients: they must send an allowed `Origin` or `Referer`; there is no missing
header bypass. Every authenticated unsafe route must be registered on the
CSRF-protected router and inherit its `require_csrf` dependency. Registration and
login remain public pre-session routes protected by strict Origin/Referer
checks. The HTTP auth test suite inventories unsafe routes and fails if a
new write route lacks protection.

Login and registration use bounded in-memory token buckets. Each request is
limited by the ASGI client IP and by the combination of that IP and the
normalized email; an email is never rate-limited globally, so one client cannot
lock an account for everyone. All attempts, including successful ones, count.
Client IP comes from the ASGI connection peer. Forwarded headers are not read
directly; behind a reverse proxy, configure Uvicorn to trust only the proxy
addresses you control. Missing or invalid peer addresses share a conservative
`unknown` bucket. The limiter is process-local, so run one application process
and one replica until a shared rate-limit store is introduced. It reduces
credential-guessing and Argon2 abuse from a source but is not DDoS protection.
The CSRF secret is domain-separated in an
HMAC-SHA256 derivation from the raw session cookie; the token is returned only
in the `/csrf` JSON body, is never stored, and is compared in constant time.
The authentication cookie expires at the session's database absolute expiry;
the server-side idle and absolute expiration checks remain authoritative.
Missing or invalid sessions return 401; an authenticated request with an
untrusted origin or missing/invalid CSRF header returns 403.

CORS allows only the exact configured frontend origins, credentials, `GET`,
`POST`, `PATCH`, and `DELETE`, and the `Content-Type` and `X-CSRF-Token`
headers. CORS is a browser policy; the server independently checks
Origin/Referer on registration/login and Origin plus CSRF on state-changing
authenticated requests.

## Budget API

Authenticated users can list, retrieve, create, update, and delete monthly
budgets at `/api/budgets`. Write requests require the session CSRF token.
Budgets are either overall (`category_id: null`) or for an active expense
category owned by the user. Limits are positive integer paise no greater than
the JavaScript safe-integer maximum. `month_start` must be the first day of its
month. PostgreSQL partial unique indexes enforce one overall budget per user
and month and one budget per user, category, and month; duplicates return HTTP
409.

Each response includes actual expense spending, remaining paise, and
`percent_used_basis_points` (one percentage point is 100 basis points; 10,000
means 100%). Percentages use integer arithmetic rounded half-up. Actual
spending includes non-deleted expense transactions dated in the calendar month
`[month_start, first day of next month)`. Income and goal allocations are
excluded. Overall budgets include categorized and uncategorized expenses;
category budgets include only that category. Remaining amounts may be
negative when spending exceeds the limit. Calculations use grouped database
queries and do not issue a query per budget.

For precision, `limit_paise` is returned as a JSON integer because request
validation bounds it to JavaScript's safe-integer range. The response fields
`actual_spending_paise`, `remaining_paise`, and `percent_used_basis_points` are
base-10 decimal strings. The backend retains exact integer arithmetic for all
calculations and converts these values to strings only when building the API
response. Frontend exact arithmetic must parse these strings as `BigInt`; do not
convert them to `Number`. A chart may convert a separately scaled ratio to a
number for display.

Services stage changes without committing. The HTTP request boundary commits
successful mutations and rolls back validation, uniqueness, or database
failures. Archived categories remain valid on existing budgets and are still
included in their historical spending; they cannot be selected for a new
budget or newly assigned by an update.

## Savings goals and allocation ledger

Goals are tenant-scoped and soft-deleted. Create and update requests support a
name, optional description, positive target in integer paise no greater than
the JavaScript safe-integer maximum, and optional target date. Past target dates
are rejected using the product's `Asia/Kolkata` financial date convention.
Updating a target below the amount currently allocated to that goal returns
HTTP 409. Deleted and foreign goals are both reported as not found. Repeating a
delete also returns 404.

Contributions and withdrawals are append-only `goal_entries`; the API has no
entry update or delete operation. Entries receive their effective date from
the server. A contribution records a virtual allocation from one owned active
account to one active goal. A withdrawal releases only the outstanding amount
for that exact goal/account pair. Both use positive safe-integer paise and
return updated goal and account summaries. They do not create transactions or
change actual account balances.

The allocation ledger derives the current net as contributions minus
withdrawals. An account's available-to-spend amount is its actual balance minus
all net goal allocations in that account. Contributions are rejected when they
exceed that available amount or would make the goal's aggregate exceed
`Number.MAX_SAFE_INTEGER` paise. Expenses are rejected if the resulting
available-to-spend would be negative, including when allocations are zero.
Income remains allowed and increases actual balance. Opening-balance edits are
locked after any transaction or goal entry has been recorded for the account.
Account balance, allocation, and available-to-spend values are calculated in a
single SQL statement snapshot.

Contributions are not currently capped at the goal target. The API can return a
negative `remaining_target_paise` after overfunding; whether to reject
overfunding remains a product decision.

Contributions and withdrawals lock the goal first, then the account. Expense
and income creation and opening-balance updates lock the account; transaction
creation then takes a shared lock on the selected category. Goal deletion locks
the goal, computes outstanding allocations grouped by account, locks affected
accounts in ascending UUID order, appends one compensating withdrawal per
positive account allocation, and soft-deletes the goal in the same request
transaction. Services do not commit. A request failure rolls back entries and
deletion together. Original ledger entries are never edited or deleted. Goal
deletion releases the reservation without changing actual account balances.

Goal lists and ledger histories are paginated with `offset` and `limit` (1–100)
and use deterministic ordering. Aggregations are grouped in SQL rather than
queried once per goal or account.

Budget aggregate responses use decimal strings for exact client transport;
`limit_paise` remains a safe-range JSON integer. Budget-list pagination remains
deferred.

## Run tests

```sh
python -m pytest
```

Without `POSTGRES_TEST_DATABASE_URL`, PostgreSQL-specific tests skip and the
unit/SQLite suite runs without PostgreSQL. To enable PostgreSQL integration,
configure a **dedicated local test database**, separate from the application
database (normally `vibewealth_test`), and set `POSTGRES_TEST_DATABASE_URL` in
the shell. The fixture checks the URL uses the `postgresql+psycopg` driver, a
local host, the configured PostgreSQL port, and a database name different from
the application database. Each fixture creates tables in a unique
`model_test_<uuid>` schema and drops that schema with `CASCADE` afterward. This
cleanup is destructive to that temporary schema; never use the development,
production, or any database containing data to preserve. Example shape only:

```sh
export POSTGRES_TEST_DATABASE_URL='postgresql+psycopg://test_user:test_password@localhost:5432/vibewealth_test'
python -m pytest -v tests/test_models_postgres.py
```

The URL above contains example-only credentials; use the credentials you
configured for the dedicated test database. Do not paste a real URL into a
tracked file or terminal transcript.

The separate opt-in connection smoke test uses the application's configured
database URL and executes only `SELECT 1`; enable it only after verifying that
configuration deliberately:

```sh
RUN_POSTGRES_INTEGRATION=1 python -m pytest tests/test_database.py -k postgresql_connection
```

## Manage the local PostgreSQL database

Run these commands in WSL2 Ubuntu from `backend/`. PostgreSQL is bound to
`127.0.0.1`; set `POSTGRES_PORT` in `.env` to change the host port.

Start PostgreSQL in the background:

```sh
docker compose up -d db
```

Inspect service state and logs:

```sh
docker compose ps
docker compose logs -f db
```

Check readiness from inside the container:

```sh
docker compose exec db sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Stop the container while keeping database data:

```sh
docker compose down
```

Reset the local database by stopping it and removing its named data volume:

```sh
docker compose down -v
```

The reset command permanently deletes local PostgreSQL data. The named volume
is `vibewealth_postgres_data`.

## Manage database migrations

Run Alembic commands from `backend/` in WSL2 with the Linux virtual environment
active and `.env` configured. The migration environment reuses the same
validated connection URL and `Base.metadata` as the FastAPI application. The
Alembic configuration file contains no database credentials. Migrations run
only when explicitly invoked; application startup does not alter the schema.
Before any command that connects to PostgreSQL, verify the effective database
target. `alembic upgrade` changes that database's schema; do not point it at a
database whose schema is not intended to be migrated.

The current migration head is `6b9c2f1d4a80` (`add goal descriptions and goal-scoped ledger index`)
and includes the approved initial schema, authentication sessions, and the goal
description/history-index changes. Create a
migration only after adding or changing ORM models:

```sh
alembic revision --autogenerate -m "description"
```

Review every generated migration before applying it. Existing database tables
without corresponding ORM metadata are excluded from autogenerated drop
operations.

Apply migrations:

```sh
alembic upgrade head
```

Roll back one migration:

```sh
alembic downgrade -1
```

Check the current revision and migration history:

```sh
alembic current
alembic history
```

Check whether model metadata differs from the current database schema:

```sh
alembic check
```
