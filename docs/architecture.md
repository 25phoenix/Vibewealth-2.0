
# VibeWealth 2.0 – System Architecture

## 1. Overview

VibeWealth has a React frontend and a separately implemented FastAPI backend.
The frontend uses backend cookie authentication, reads real accounts and
active categories, and connects transactions, budgets, savings goals, and
dashboard summaries through authenticated APIs. The assistant continues to
use a mock service. The backend provides PostgreSQL-backed
authentication, account reads/metadata updates, income/expense transaction
operations, monthly budget CRUD and actual-spending calculations, and
savings-goal allocation APIs. AI operations remain future work.

## 2. Frontend Architecture

Technology:
- React
- TypeScript
- Vite
- Tailwind CSS
- shadcn/ui
- Recharts

Responsibilities:
- Render the user interface.
- Manage client-side navigation and shared finance state.
- Handle forms and user interactions.
- Display financial analytics.
- Communicate with backend APIs.
- Display AI assistant conversations.

Current implementation:
- `src/pages/` composes the dashboard, transactions, budgets, savings goals, assistant, and settings screens.
- `src/components/ui/` contains shadcn/ui components generated with the shadcn CLI. Application components build on these primitives instead of defining a separate component framework.
- `src/hooks/FinanceProvider.tsx` receives a mock repository and assistant service through interfaces. Each authenticated session gets fresh instances, keyed by an authentication-session generation; logout unmounts and discards that session's mock state.
- `src/hooks/AuthProvider.tsx` restores the backend cookie session before mounting private finance pages. Login, registration, CSRF state, and logout are handled by the API auth service.
- `src/hooks/AccountCategoryProvider.tsx` loads authenticated account and active-category DTOs into state scoped to the current auth-session generation. It provides independent retries and routes data-request 401 responses through the existing logout flow.
- `src/hooks/TransactionsProvider.tsx` and `src/services/api/transactionsApi.ts` manage transaction list/create state separately from the mock finance repository. The provider resets on auth-session changes, ignores stale requests, retries list failures, and refreshes account data independently after a successful create. A committed create remains successful if either refresh fails.
- `src/hooks/BudgetsProvider.tsx` and `src/services/api/budgetsApi.ts` manage current-month budget CRUD and server-calculated spending independently from mock finance state. Aggregate values remain decimal strings and use `BigInt` for exact comparisons and formatting; mutations invalidate older reads before refresh.
- `src/hooks/SavingsGoalsProvider.tsx` and `src/services/api/goalsApi.ts` manage paginated goals, goal CRUD, account-linked contributions/withdrawals, and paginated append-only ledger history. Successful allocation changes refresh goals, the active ledger, and account balances. Deletion relies on the backend's atomic compensating-entry behavior.
- `src/hooks/DashboardProvider.tsx` and `src/services/api/dashboardApi.ts` load the authenticated summary, deduplicate in-flight reads, discard stale-session results, and refresh after successful transaction, budget, and goal mutations.
- `src/services/api/` contains the shared credentialed fetch client and typed authentication, account, category, transaction, budget, goal, and dashboard endpoints. API-backed providers reset on auth-session changes and ignore stale requests; they never fall back to sample records.
- `src/services/financeCalculations.ts` derives mock/demo category, budget, goal, and transaction summaries from typed records. The live dashboard uses backend-provided summary DTOs.
- `src/services/mockAssistantService.ts` supplies sample-data-aware responses. It is not a language model integration.
- All six pages are loaded on demand with `React.lazy` and a shared `Suspense` fallback.
- `src/mocks/finance.ts` is the only source for seeded finance data. UI components do not import mocks directly.
- `src/index.css` owns semantic design tokens, including light/dark surfaces, brand, status, and chart colors. Components consume those tokens so a later Hallmark redesign can change presentation without changing finance logic.
- Financial amounts use integer paise for calculations and are formatted only at the presentation boundary. The budget API preserves potentially unbounded spending totals and basis points as decimal strings; the frontend retains those strings and uses `BigInt`.

Assistant interactions update in-memory sample state for the authenticated
session only. A new session generation creates a fresh mock repository and
assistant service, including on same-user relogin; logout unmounts the session
subtree. Account, active-category, transaction, budget, savings-goal, and
dashboard state is session-scoped and comes from the backend. Potentially
unbounded budget and dashboard aggregate strings are retained without numeric
coercion and formatted with exact `BigInt` arithmetic. Finance mock state is
not persisted in browser storage. Preferences use local browser storage.

### Frontend finance API integration contract

- **Ownership and isolation:** every financial record belongs to an authenticated user. FastAPI derives that user from the authenticated request; it must not trust a client-supplied owner ID. Every read, update, and delete is scoped to that user. The frontend's single mock repository is demo state, not a tenant boundary.
- **Financial data access:** the UI calls service/repository interfaces. The mock repository and assistant service are newly created for each authentication session and discarded at logout; they are demo state, not a tenant boundary. Account/category, transaction, budget, and goal API services send authenticated requests through the shared client; the backend owns database access and authoritative financial calculations. Assistant requests will go through the backend, which loads only the authenticated user's relevant context and invokes controlled tools.
- **Validation:** browser form validation improves usability but is never a security boundary. FastAPI validates request schemas, record ownership, category/month uniqueness, dates, and positive safe integer amounts in paise before persistence or calculation.
- **Money and currency:** the initial product is INR-only. Stored amounts and limits are integer paise; currency formatting is presentation-only. Do not relabel paise as another currency without an explicit conversion and source-currency model.
- **Transaction dates:** ordinary transactions represent completed activity and must have a valid date no later than the current `Asia/Kolkata` financial date. The UI sends date-only values without converting them through UTC or using device-local time. Scheduled transactions are a separate future feature and must not be represented as completed transactions.
- **Transaction creation retries:** each logical frontend submission sends a cryptographically random `Idempotency-Key`. PostgreSQL stores the key and normalized request fingerprint on the transaction row under a user-scoped unique constraint. The transaction and replay record therefore commit atomically; an identical retry returns the original result, while a changed payload using the same key returns HTTP 409. The frontend keeps the exact payload in memory while the form remains mounted and stores only `{version, userId, key}` in per-user `sessionStorage`. After reload or same-user provider teardown, authenticated `GET /api/transactions/operations/{key}` resolves a completed transaction without another POST. A confirmed not-found result preserves the key for a same-key retry. Only create HTTP 422 responses and the exact backend `Account not found` HTTP 404 response are definitive rejections; 408, other statuses, network failures, and unknown errors preserve the key and require resolution or retry of the same operation. Malformed or unsupported markers are preserved; a syntactically valid key scoped to the current user is resolved first. If that is impossible, the user must explicitly confirm reconciliation after reviewing transaction history, with a warning that history cannot identify every operation and duplicate prevention cannot be guaranteed after abandonment. Closing the form never removes the durable marker. This storage lasts only for the current tab session and does not guarantee recovery after tab closure or a separate browser session. Transaction editing and deletion remain unsupported.
- **Budget calculations:** backend budgets are user-owned, monthly records with a first-of-month `month_start`, a positive integer-paise limit, and either a null category for an overall budget or an active user-owned expense category. Partial unique indexes enforce one overall budget per user/month and one per user/category/month. Actual spending sums non-deleted expense transactions in `[month_start, first day of next month)`; income and goal entries are excluded. Overall spending includes categorized and uncategorized expenses, while category budgets include only that category. Remaining paise can be negative. `percent_used_basis_points` is hundredths of a percentage point, calculated using integer arithmetic with half-up rounding. The API returns `limit_paise` as a safe-range JSON integer and `actual_spending_paise`, `remaining_paise`, and `percent_used_basis_points` as exact decimal strings. Backend calculations remain integer-based; frontend exact arithmetic must use `BigInt` and must not convert these strings to `Number`. Archived categories remain valid for historical budgets but cannot be selected for new or reassigned budgets. Frontend overview reconciliation remains a separate presentation calculation.
- **Savings goals:** contributions and withdrawals are virtual allocations recorded in an append-only ledger, not income, expenses, or physical transfers. They do not change actual account balances. Each account's available-to-spend is its actual balance minus its net goal allocations. Withdrawals cannot exceed the allocation for the same goal/account pair. Goal deletion appends compensating withdrawals for every outstanding account allocation and soft-deletes the goal in one transaction; ledger history remains intact.
- **Budget frontend contract:** aggregate spending, remaining amount, and basis-point values are retained as decimal strings to preserve exact values beyond JavaScript's safe-integer range. The frontend uses `BigInt` for exact operations. Budget lists are filtered by month and are not paginated; goal and ledger lists use offset/limit pagination.
- **Dashboard summary:** `GET /api/dashboard/summary` returns a server-selected `Asia/Kolkata` financial date and month interval, account totals, monthly cash flow, current-month budgets, a paginated goal subset with total count, and the four most recent transactions. It is authenticated and tenant-scoped. Potentially unbounded paise aggregates and budget basis points are decimal strings; individual transaction amounts and goal totals/targets remain safe JSON integers. The UI refreshes the summary after successful transaction, budget, or goal mutations and does not use mock data when the request fails.
- **Async frontend contracts:** `FinanceRepository.load` and all repository mutations return Promises. The repository may expose a synchronous cached snapshot and subscription for React rendering, while network operations remain asynchronous. The provider receives a repository implementation by interface. `AssistantService.reply` also returns a Promise and is injected separately. Implementations surface loading and operation failures to the UI.
- **Remaining mock-backed surfaces:** assistant responses and profile edits use mock/local behavior. Assistant integration should use authenticated services and preserve server errors; financial validation and calculations remain authoritative on the backend.

Suggested frontend structure:

frontend/src/
- components/
  - ui/
  - dashboard/
  - transactions/
  - budgets/
  - goals/
  - assistant/
- pages/
- layouts/
- hooks/
- services/
- types/
- mocks/
- lib/

## 3. Backend Architecture (Implemented Foundation)

Technology:
- Python
- FastAPI
- SQLAlchemy
- PostgreSQL

Implemented responsibilities:
- Cookie-based registration, login, current-user lookup, CSRF-token, and logout
  operations.
- Tenant-scoped account listing, retrieval, balance calculation, and permitted
  metadata updates.
- Tenant-scoped listing of active categories for transaction selection.
- Tenant-scoped income/expense creation, retrieval, filtering, and pagination.
- Tenant-scoped monthly budget CRUD and grouped transaction-derived spending
  calculations for overall and expense-category budgets.
- Tenant-scoped savings-goal CRUD, append-only contributions/withdrawals, and
  automatic allocation release on goal deletion.
- Account responses with actual balance, net goal allocations, and
  available-to-spend; expense creation cannot make available-to-spend negative
  or consume allocated funds.
- Integer-paise balances with soft-deleted transactions excluded.
- PostgreSQL schema management through Alembic.

Broader financial analytics and AI orchestration are not implemented.

## 4. Database Architecture (Current Schema)

Registered SQLAlchemy entities:

- Users and authentication sessions.
- Accounts, categories, and transactions.
- Budgets, savings goals, and goal entries.
- Assistant conversations and messages.

Financial models have user ownership constraints. Account, transaction, budget,
and goal services scope every query to the authenticated user. Registration
creates one default cash, bank, or wallet account with a zero opening balance
and seeds per-user categories. Additional account creation and account deletion
are not exposed by the current API.

Money is stored and calculated in integer paise. An account's opening balance
is the starting balance at the beginning of `opening_balance_as_of`; transactions
on that date are included. Current and historical balances add live income and
subtract live expenses through the requested date. Deleted transactions are
excluded. Transaction creation checks the resulting closing balance for every
affected date through today against JavaScript's safe-integer range using
integer paise. Goal contributions and withdrawals never enter transaction
totals or change actual balances. Account responses derive net goal allocations
from the ledger and report available-to-spend as actual balance minus those
allocations. Goal mutations lock the goal then account; goal deletion locks
affected accounts in ascending UUID order and appends compensating withdrawals
before soft-deleting the goal in the same request transaction. Expense and
income creation lock the account before the category; opening-balance updates
lock the account. Account balance, allocation, and available-to-spend values
are read from one SQL statement snapshot. Goal allocation aggregates are capped
at JavaScript's safe-integer limit. Contributions may currently exceed a goal's
target; in that case `remaining_target_paise` is negative, pending a product
decision on target caps.

## 5. AI Architecture (Planned)

The AI assistant will use Google Gemini.

The assistant will interact with controlled backend tools rather than directly accessing the database.

Potential tools:

- get_monthly_summary
- get_category_spending
- get_recent_transactions
- get_budget_status
- get_savings_goals
- calculate_goal_projection

Financial calculations must be performed by backend code.

## 6. Context Management (Planned)

The assistant will use four context layers:

1. User profile and preferences.
2. Current financial information.
3. Relevant conversation history.
4. Long-term user memories and goals.

Only relevant context should be included in each AI request.

## 7. Frontend Integration Strategy

During initial frontend development:
- Use mock financial data.
- Keep mock data separate from UI components.
- Create typed interfaces for financial entities.
- Place API interactions behind service modules.
- Avoid hardcoding backend implementation details into components.
- Keep semantic design tokens and shared shadcn/ui components at the presentation boundary.
- Keep calculations independent of page layout and visual components.

This will allow mock services to be replaced with real API services later.

## 8. Security

- API keys must never be exposed in frontend code.
- Account, transaction, budget, and savings-goal reads require an authenticated
  session, and their
  database queries are scoped to that user.
- Account metadata updates, transaction creation, budget mutations, and
  savings-goal/ledger mutations require trusted Origin and CSRF validation.
- Registration and login require exact Origin/Referer validation and use
  bounded process-local rate limits.
- PostgreSQL account row locks serialize opening-balance changes with
  transaction creation.
- AI tools must not have unrestricted database access.
- Financial write operations must require explicit confirmation.

The frontend connects to the authenticated API for registration, login,
session restoration, CSRF tokens, and logout. Settings consumes authenticated
account and active-category reads. Transactions, budgets, savings goals, and
dashboard summaries use the authenticated backend; assistant responses remain
mock-backed. The backend rate-limit state is
process-local and requires a single process/replica until a shared store is
introduced.

## 9. Deployment (Planned)

- Frontend: Vercel
- Backend: Render or equivalent
- Database: Managed PostgreSQL
