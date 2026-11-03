
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
- Manage client-side navigation.
- Handle forms and user interactions.
- Display financial analytics.
- Communicate with backend APIs.
- Display AI assistant conversations.

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
