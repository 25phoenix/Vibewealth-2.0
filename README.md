# VibeWealth 2.0

VibeWealth is a personal finance application in development. The repository
contains a React frontend and a separate FastAPI backend. Frontend registration,
login, session restoration, and logout use the backend. Settings loads
authenticated account balances and active categories. Transaction listing and
creation, budgets, and savings goals are also backend-connected. Dashboard
summaries now come from a tenant-scoped backend endpoint; assistant conversations now use the persistent authenticated API; generation remains disabled pending local-provider approval and benchmarking.

## Current implementation

- **Frontend:** React, TypeScript, Vite, Tailwind CSS, shadcn/ui, and Recharts.
  It has dashboard, transactions, budgets, savings goals, assistant, and
  settings pages. Authentication uses the backend's cookie session.
  Transactions are listed and created through the authenticated backend.
  Dashboard summaries and assistant conversation history use the authenticated backend. Assistant generation remains disabled pending verified token accounting, endpoint approval and a real-machine benchmark. The mock
  repository and assistant service
  are created after each login, including a same-user relogin; mock finance
  state is not persisted. Account balances and active categories are loaded
  from the authenticated backend. Transaction creation uses real account and
  category IDs plus server-enforced idempotency. Ambiguous outcomes retry with
  the same operation key and payload. The key and user ID are retained in
  tab-scoped `sessionStorage` (no transaction details) and resolved through an
  authenticated operation lookup after reload or same-user reauthentication.
  This survives reloads/provider remounts in the same tab, not tab closure or a
  separate browser session. Only the backend's transaction rejection contract
  (HTTP 422, or HTTP 404 with `Account not found`) proves no transaction was
  created; timeouts, other statuses, and network failures keep the key unresolved.
  Malformed or unsupported markers are retained; a safe same-user key is first
  resolved with the backend, otherwise the UI requires explicit reconciliation
  after history review and warns that duplicate prevention cannot be guaranteed.
  Later list/account refresh failures do not turn a committed create into a
  failure. Transaction dates remain date-only; future
  validation uses the `Asia/Kolkata` financial date, independent of device
  timezone. Editing and deletion are unavailable.
  Preferences are stored locally. The UI uses INR and integer paise.
- **Backend:** FastAPI, SQLAlchemy 2.x, PostgreSQL, and Alembic. It has database
  models and migrations for users, accounts, categories, transactions, budgets,
  savings goals and entries, assistant conversations and messages, and
  authentication sessions. Cookie-based registration, login, current-user,
  CSRF-token, and logout endpoints are implemented, along with authenticated
  account, category-selection, and transaction endpoints and health endpoints.
  Tenant-scoped monthly budget APIs and savings-goal/allocation-ledger APIs are
  also available. Transactions can be filtered and paginated, and account
  balances and budget totals use integer-paise arithmetic. Budget API limits are
  JSON integers; potentially large spending, remaining, and basis-point totals
  are returned as exact decimal strings.
- **Not enabled yet:** assistant provider generation. **Not implemented yet:** transaction
  editing/deletion, account creation/deletion,
  account recovery and a benchmark-approved live AI provider.
  The assistant frontend uses persistent conversations, lifecycle recovery and explicit retry/abandon; it has no mock-answer fallback. Settings consumes
  the backend account-list (including balances) and active-category APIs. The
  Transactions page consumes backend transaction list/create APIs; transaction
  editing and deletion are not exposed by the backend. Dashboard summaries are backend-connected; assistant generation is disabled by default.

The current backend is a development foundation, not a production launch
declaration. See the backend guide for security, database, and testing limits.

## Run the frontend

Use Node.js 24 and npm 11. From the repository root:

```sh
cd frontend
npm ci
npm run dev
```

Frontend checks are listed in [frontend/README.md](frontend/README.md).

## Run the backend

The backend setup, local PostgreSQL Compose service, environment configuration,
migrations, authentication behavior, and PostgreSQL test safeguards are
documented in [backend/README.md](backend/README.md). The project’s database
workflow uses Docker Engine and Compose in WSL2 Ubuntu.

## Repository layout

- `frontend/` — React app with backend authentication, account/category reads, transactions, budgets, savings goals, and dashboard summaries; the assistant uses persistent authenticated history with generation disabled by default.
- `backend/` — FastAPI application, SQLAlchemy models, migrations, and tests.
- `docs/` — product requirements and architecture notes.

## Product constraints

- INR-only launch with money stored as integer paise.
- No direct bank integration in the initial version; transaction imports are
  future work.
- Goal contributions are virtual allocations, separate from income and expense
  transactions.
- Financial data operations are scoped to the authenticated user by the backend.

## Project documentation

- [Backend setup and API details](backend/README.md)
- [Frontend setup and structure](frontend/README.md)
- [Product requirements](docs/requirements.md)
- [System architecture](docs/architecture.md)
