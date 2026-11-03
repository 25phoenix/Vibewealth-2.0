
# GoalDigger/VibeWealth 2.0

An AI-powered personal finance management platform designed to help young adults understand, manage, and improve their financial habits.

## Vision

VibeWealth combines personal finance management with a context-aware AI assistant. Users can track their income and expenses, manage budgets, set savings goals, and receive personalised financial insights.

Unlike a generic chatbot, the AI assistant will use the user's actual financial data, preferences, goals, and relevant conversation history to provide contextual responses.

## Core Features

- User authentication and financial profiles
- Income and expense tracking
- Transaction categorisation
- Monthly budgets
- Savings goals and progress tracking
- Financial dashboard and analytics
- Context-aware AI financial assistant
- Personalised insights and spending recommendations

## Technology Stack

### Frontend
- React
- TypeScript
- Vite
- Tailwind CSS
- shadcn/ui
- Recharts

### Backend (planned)
- Python
- FastAPI
- SQLAlchemy
- PostgreSQL

### AI (planned)
- Google Gemini API / FinGPT
- Tool calling
- Context management
- Conversation memory

## Current Development Status

The project is currently in its frontend development phase.

The initial frontend will use mock financial data and simulated interactions. Backend integration and AI functionality will be implemented in subsequent phases.

## Run the frontend

The frontend lives in `frontend/` and uses npm. With Node.js 20.19+ or 22.12+ installed:

```sh
cd frontend
npm install
npm run dev
```

See `frontend/README.md` for TypeScript, lint, and production build checks.

## Project Structure

- `frontend/` – React application
- `backend/` – Backend application
- `docs/` – Requirements and architecture documentation

## Development Goals

Build a polished, responsive, production-oriented personal finance application with a genuinely useful AI assistant.

## Important Constraints

- No direct bank integrations in the initial version.
- Transactions will be entered manually or imported through CSV.
- No money transfers or autonomous financial transactions.
- Financial information must remain private and isolated between users.
