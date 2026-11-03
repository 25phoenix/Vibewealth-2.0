
# VibeWealth 2.0 – Product Requirements

## 1. Target Audience

Young adults, students, and early-career professionals who want to understand and manage their personal finances.

## 2. Core User Journey

1. A user creates an account.
2. They provide basic financial profile information.
3. They add income and expense transactions.
4. They organise their spending into categories.
5. They establish monthly budgets.
6. They create savings goals.
7. They monitor their finances through a dashboard.
8. They interact with an AI assistant that understands their financial situation.

## 3. Functional Requirements

### 3.1 Dashboard

The dashboard should display:
- Total balance
- Monthly income
- Monthly expenses
- Savings for the current month
- Budget utilisation
- Recent transactions
- Spending breakdown by category
- Monthly spending trends
- Savings goal progress

### 3.2 Transactions

Users should eventually be able to:
- Add income and expense transactions.
- Edit and delete transactions.
- Assign categories.
- Add descriptions and dates.
- Filter and search transactions.
- Import transactions through CSV.

### 3.3 Budgets

Users should be able to:
- Create monthly budgets.
- Set category-specific spending limits.
- View current spending against budgets.
- Identify categories approaching their limits.
- Review historical budget performance.

### 3.4 Savings Goals

Users should be able to:
- Create savings goals.
- Define a target amount and deadline.
- Track progress.
- View the remaining amount.
- Receive suggestions for reaching their goals.

### 3.5 AI Financial Assistant

The assistant is a central feature of VibeWealth.

It should eventually be able to:

- Answer questions about the user's finances.
- Analyse spending habits.
- Compare spending across different periods.
- Explain budget utilisation.
- Help users plan savings goals.
- Consider upcoming expenses when answering financial questions.
- Remember relevant user preferences and long-term goals.
- Provide personalised financial suggestions.

Example:

User: Can I afford headphones worth ₹15,000 this month?

Assistant: The assistant should examine the user's actual financial data, existing budgets, upcoming expenses, and savings commitments before responding.

The assistant must not invent financial figures.

## 4. Frontend Requirements

The frontend should:
- Be responsive across desktop, tablet, and mobile.
- Have a consistent design system.
- Use reusable components.
- Provide intuitive navigation.
- Include loading, empty, and error states.
- Use realistic mock data during initial development.
- Keep frontend components separate from business logic and API integration.

## 5. Non-Functional Requirements

- Secure authentication.
- User-level financial data isolation.
- Input validation.
- Accessible UI components.
- Maintainable and modular code.
- Good performance.
- Clear error handling.

## 6. Initial Development Scope

Phase 1: Frontend using mock data.

Phase 2: Backend, database, authentication, and financial operations.

Phase 3: AI assistant and context management.

Phase 4: Testing, deployment, and refinement.
