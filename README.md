# VibeWealth 2.0

VibeWealth is a personal finance application in development. The repository
currently contains a polished frontend prototype and a separate FastAPI backend
foundation. The frontend still uses sample finance data and is not connected to
the backend.

## Current implementation

- **Frontend:** React, TypeScript, Vite, Tailwind CSS, shadcn/ui, and Recharts.
  It has dashboard, transactions, budgets, savings goals, assistant, and
  settings pages. Finance records and assistant replies are mock data held in
  browser memory; preferences are stored locally. The UI uses INR and integer
  paise.
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
- **Not implemented yet:** frontend-to-backend integration,
  transaction editing/deletion, account creation/deletion,
  account recovery, a persistent assistant service, and a live AI provider.
  The assistant in the frontend is a deterministic mock. The implemented
  account, transaction, budget, and savings-goal APIs are not connected to the
  frontend yet.

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

- `frontend/` — React prototype and mock finance/assistant services.
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
