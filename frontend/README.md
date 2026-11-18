# VibeWealth frontend

The frontend is a React, TypeScript, and Vite application. Sign-in, registration, session restoration, and sign-out use the FastAPI backend's cookie-based authentication. Settings loads authenticated account balances and active categories. Transactions lists and creates backend transactions; Budgets and Savings Goals use authenticated backend reads and mutations. The dashboard loads a tenant-scoped financial summary from the backend. Assistant conversations, history, deletion, turn recovery and retry/abandon use the authenticated API. Generation remains disabled until a local provider passes the approval and benchmark gates. Mock finance state exists only in memory for one authenticated session and is recreated on every login, including when the same user signs back in; preferences are stored locally.

## Run locally

Use Node.js 24 and npm 11 (the installed Vite and shadcn CLI versions support this environment). From this directory:

```sh
npm ci
npm run dev
```

## Connect to the local backend

The frontend API base URL is configured with `VITE_API_BASE_URL`. The default
is `http://localhost:8000`. To override it, copy `.env.example` to `.env` and
set a local backend URL; do not put credentials or secrets in Vite variables.

Start PostgreSQL and the backend using the setup in
[`../backend/README.md`](../backend/README.md), then start Vite. Keep the
frontend origin at `http://localhost:5173` and use the same `localhost` host in
the API URL so the backend's exact-origin CORS and cookie configuration match.

On startup, the app requests `/api/auth/me` to restore an existing session. If
the session is valid, it loads a session-bound CSRF token in memory. Login and
registration use the backend's HttpOnly cookie; unsafe requests such as logout
send the token in `X-CSRF-Token`. Session and CSRF tokens are never stored in
browser storage or read from cookies by JavaScript. If the server accepts login
or registration but session verification fails, the app offers a retry that
checks the existing cookie without resubmitting credentials.

Authentication is connected to the backend. Settings reads accounts (including
opening/current balances, goal allocations, and available-to-spend) and active
income/expense categories through the typed API services. Account/category
requests use the shared credentialed client and are scoped to the authenticated
session. A 401 follows the existing logout flow; failed loads show a
resource-specific retry and never fall back to mock records. Transactions are
listed from `GET /api/transactions` with backend account, category, type, date,
and offset/limit filters; descriptions can be searched within the loaded page.
Creation uses `POST /api/transactions`, the shared CSRF-aware client, and exact
integer-paise conversion. Each logical create uses a cryptographically random
`Idempotency-Key`, retained with its exact payload for retry if the response is
ambiguous. The backend replays the original transaction for the same key and
payload and returns 409 if that key is reused with different content. After an
ambiguous result, the form freezes the payload and retries with the same key;
it does not claim the write failed. The frontend stores only the opaque key,
user ID, and record version in per-user `sessionStorage`; amounts, descriptions,
notes, account/category IDs, cookies, and CSRF tokens are not stored there. On
reload or provider teardown, `GET /api/transactions/operations/{key}` resolves
the operation for the authenticated owner. A found transaction is recovered
without another POST. A confirmed not-found response keeps the same key for the
user to re-enter the details and retry; network/server errors preserve the key
and block new logical submissions. The marker survives reloads and provider
remounts in the same tab, but not necessarily tab closure or a separate browser
session. Logging out preserves it; a different user has a separate storage key
and cannot resolve it. Only HTTP 422 and the backend's exact `Account not found`
HTTP 404 are treated as definitive create rejections. HTTP 408, other 4xx/5xx,
network errors, and unknown failures preserve the key and require resolution or
a same-key retry. If metadata is malformed, a valid same-user key is attempted
against the resolver; otherwise the marker remains until a user confirms
reconciliation after reviewing history. History cannot guarantee whether an
unidentified operation committed, and abandonment warns duplicate prevention
can no longer be guaranteed. Closing the dialog preserves the marker. A
confirmed creation closes the dialog even
if the subsequent list or account refresh fails; each resource can be retried
without posting the transaction again. The transaction date defaults to the
current `Asia/Kolkata` financial date and remains date-only. Failed definitive
submissions preserve form values. The backend currently exposes no transaction
update/delete routes. Assistant history is persistent; authenticated profile editing is unavailable. A new
mock repository and assistant service are created for each authentication
session; logout discards that session's mock state. Budget and goal API state is
kept in separate session-scoped providers and never falls back to mock data.

## Checks

```sh
npm run typecheck
npm run lint
npm test
npm run build
```

## Frontend structure

- `src/components/ui/` contains shadcn/ui primitives generated and managed with the shadcn CLI.
- `src/components/` contains reusable application components; page-level compositions live in `src/pages/`.
- `src/types/` defines mock finance, preference, assistant, and backend API DTO contracts. Monetary DTOs use integer paise; unbounded budget and dashboard aggregates remain decimal strings and use `BigInt` for exact calculations.
- `src/mocks/` contains sample finance records for unconnected areas. `src/services/api/` contains the shared client and typed auth/account/category/transaction/budget/goal/dashboard/assistant services; mock repository and assistant boundaries remain separate from API DTOs.
- `src/hooks/` provides shared mock-finance state, session-scoped account/category, transaction, budget, savings-goal, and dashboard API state, and conversation behavior.
- `src/index.css` centralizes semantic color, surface, chart, and status tokens for theme changes and future visual refinement.

The dashboard, transactions, budgets, savings goals, assistant, and settings are available from the responsive sidebar. All six pages load on demand with a shared loading fallback. Dashboard summaries, transactions, budgets, and savings goals use authenticated backend operations; assistant history uses authenticated persistent APIs and generation remains disabled pending approval. Dashboard totals that may exceed JavaScript's safe-integer range stay decimal strings and are formatted with `BigInt`; individual goal totals and transaction amounts use safe integer paise. A fresh mock repository and assistant service are selected for each session identity. Preferences are stored locally in the browser. Currency is fixed to INR, ordinary transactions are completed activity dated no later than today, and goal contributions are separate allocations rather than income or expense transactions. Budget aggregates retain decimal strings and use `BigInt` for exact operations; goal ledger entries are paginated and append-only.
