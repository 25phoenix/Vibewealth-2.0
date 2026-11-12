
# VibeWealth 2.0 – System Architecture

## 1. Overview

VibeWealth has a frontend prototype and a separately implemented FastAPI
backend. The frontend continues to use mock finance and assistant services; it
does not yet call the backend. The backend provides PostgreSQL-backed
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
- `src/hooks/FinanceProvider.tsx` receives a repository and assistant service through interfaces; `MockFinanceRepository` and `MockAssistantService` are injected by the app composition root.
- `src/services/financeCalculations.ts` derives dashboard, category, budget, goal, and transaction summaries from typed records.
- `src/services/mockAssistantService.ts` supplies sample-data-aware responses. It is not a language model integration.
- All six pages are loaded on demand with `React.lazy` and a shared `Suspense` fallback.
- `src/mocks/finance.ts` is the only source for seeded finance data. UI components do not import mocks directly.
- `src/index.css` owns semantic design tokens, including light/dark surfaces, brand, status, and chart colors. Components consume those tokens so a later Hallmark redesign can change presentation without changing finance logic.
- Financial amounts use integer paise throughout the domain and are formatted only at the presentation boundary.

Financial edits in the frontend currently update in-memory mock state for the
browser session. Preferences use local browser storage. The separate backend
has authentication, account, transaction, budget, and savings-goal APIs, but
the frontend has no authentication flow or API repository wired to them.

### Pre-backend integration contract

- **Ownership and isolation:** every financial record belongs to an authenticated user. FastAPI derives that user from the authenticated request; it must not trust a client-supplied owner ID. Every read, update, and delete is scoped to that user. The frontend's single mock repository is demo state, not a tenant boundary.
- **Financial data access:** the UI calls repository/service interfaces only. The future API repository sends authenticated requests; the backend owns database access and performs financial calculations. Assistant requests go through the backend, which loads only the authenticated user's relevant context and invokes controlled tools.
- **Validation:** browser form validation improves usability but is never a security boundary. FastAPI validates request schemas, record ownership, category/month uniqueness, dates, and positive safe integer amounts in paise before persistence or calculation.
- **Money and currency:** the initial product is INR-only. Stored amounts and limits are integer paise; currency formatting is presentation-only. Do not relabel paise as another currency without an explicit conversion and source-currency model.
- **Transaction dates:** ordinary transactions represent completed activity and must have a valid date no later than today. Scheduled transactions are a separate future feature and must not be represented as completed transactions.
- **Budget calculations:** backend budgets are user-owned, monthly records with a first-of-month `month_start`, a positive integer-paise limit, and either a null category for an overall budget or an active user-owned expense category. Partial unique indexes enforce one overall budget per user/month and one per user/category/month. Actual spending sums non-deleted expense transactions in `[month_start, first day of next month)`; income and goal entries are excluded. Overall spending includes categorized and uncategorized expenses, while category budgets include only that category. Remaining paise can be negative. `percent_used_basis_points` is hundredths of a percentage point, calculated using integer arithmetic with half-up rounding. The API returns `limit_paise` as a safe-range JSON integer and `actual_spending_paise`, `remaining_paise`, and `percent_used_basis_points` as exact decimal strings. Backend calculations remain integer-based; frontend exact arithmetic must use `BigInt` and must not convert these strings to `Number`. Archived categories remain valid for historical budgets but cannot be selected for new or reassigned budgets. Frontend overview reconciliation remains a separate presentation calculation.
- **Savings goals:** contributions and withdrawals are virtual allocations recorded in an append-only ledger, not income, expenses, or physical transfers. They do not change actual account balances. Each account's available-to-spend is its actual balance minus its net goal allocations. Withdrawals cannot exceed the allocation for the same goal/account pair. Goal deletion appends compensating withdrawals for every outstanding account allocation and soft-deletes the goal in one transaction; ledger history remains intact.
- **Budget API follow-up:** aggregate spending, remaining amount, and basis-point values are returned as decimal strings to preserve exact values beyond JavaScript's safe-integer range. The future frontend API adapter must retain these strings and use `BigInt` for exact operations. Budget-list pagination is deferred.
- **Async frontend contracts:** `FinanceRepository.load` and all repository mutations return Promises. The repository may expose a synchronous cached snapshot and subscription for React rendering, while network operations remain asynchronous. The provider receives a repository implementation by interface. `AssistantService.reply` also returns a Promise and is injected separately. Implementations surface loading and operation failures to the UI.
- **Future FastAPI repository:** implement the frontend contracts with authenticated HTTP calls, map server DTOs into typed domain data, refresh/update the cached snapshot only after successful responses, and preserve server errors for page-level feedback. Do not move authoritative financial validation or calculations into this client adapter.

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

The frontend is not connected to the authenticated API yet. The backend
rate-limit state is process-local and requires a single process/replica until a
shared store is introduced.

## 9. Deployment (Planned)

- Frontend: Vercel
- Backend: Render or equivalent
- Database: Managed PostgreSQL
