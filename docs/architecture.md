
# VibeWealth 2.0 – System Architecture

## 1. Overview

VibeWealth follows a modular client-server architecture.

The frontend communicates with a backend API, which handles authentication, financial operations, database access, and AI orchestration.

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

Financial edits currently update in-memory state for the browser session. Preferences use local browser storage. There is no API, authentication, or server persistence yet.

### Pre-backend integration contract

- **Ownership and isolation:** every financial record belongs to an authenticated user. FastAPI derives that user from the authenticated request; it must not trust a client-supplied owner ID. Every read, update, and delete is scoped to that user. The frontend's single mock repository is demo state, not a tenant boundary.
- **Financial data access:** the UI calls repository/service interfaces only. The future API repository sends authenticated requests; the backend owns database access and performs financial calculations. Assistant requests go through the backend, which loads only the authenticated user's relevant context and invokes controlled tools.
- **Validation:** browser form validation improves usability but is never a security boundary. FastAPI validates request schemas, record ownership, category/month uniqueness, dates, and positive safe integer amounts in paise before persistence or calculation.
- **Money and currency:** the initial product is INR-only. Stored amounts and limits are integer paise; currency formatting is presentation-only. Do not relabel paise as another currency without an explicit conversion and source-currency model.
- **Transaction dates:** ordinary transactions represent completed activity and must have a valid date no later than today. Scheduled transactions are a separate future feature and must not be represented as completed transactions.
- **Budget calculations:** for each month/category, progress is the sum of completed expense transactions in that category and month. Category/month budget pairs are unique. The overview distinguishes total allocation, spending in budgeted categories, spending in unbudgeted categories, and total actual spending; the latter two spending groups must reconcile to total actual spending.
- **Savings goals:** a contribution is an allocation towards a goal, not income or an ordinary expense. It must not be double-counted in transaction totals. A future backend should model goal allocations in a separate ledger or equivalent internal transfer model, and define how allocations relate to account balances.
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

## 3. Backend Architecture (Planned)

Technology:
- Python
- FastAPI
- SQLAlchemy
- PostgreSQL

Responsibilities:
- Authentication and authorisation.
- Transaction management.
- Budget management.
- Savings goal calculations.
- Financial analytics.
- AI assistant orchestration.

## 4. Database Architecture (Planned)

Primary entities:

- Users
- User Profiles
- Transactions
- Budgets
- Savings Goals
- Chat Sessions
- Chat Messages
- User Memories

All financial records must be associated with their authenticated user.

Money should be stored using integer minor units (paise), not floating-point values.

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
- Backend endpoints must enforce authentication.
- Financial data access must be scoped to the authenticated user.
- AI tools must not have unrestricted database access.
- Financial write operations must require explicit confirmation.

## 9. Deployment (Planned)

- Frontend: Vercel
- Backend: Render or equivalent
- Database: Managed PostgreSQL
