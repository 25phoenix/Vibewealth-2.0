# VibeWealth frontend

The frontend is a React, TypeScript, and Vite application. It currently uses clearly labeled sample INR data and a mock assistant; there is no backend, authentication, or persistent financial storage.

## Run locally

Use Node.js 24 and npm 11 (the installed Vite and shadcn CLI versions support this environment). From this directory:

```sh
npm install
npm run dev
```

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
- `src/types/` defines the finance, preference, and assistant data contracts. Money is represented as integer paise.
- `src/mocks/` contains sample finance records. `src/services/` provides calculations, validation, and asynchronous repository/assistant boundaries, so the mock implementations can later be replaced by API-backed implementations.
- `src/hooks/` provides shared finance state and conversation behavior.
- `src/index.css` centralizes semantic color, surface, chart, and status tokens for theme changes and future visual refinement.

The dashboard, transactions, budgets, savings goals, assistant, and settings are available from the responsive sidebar. All six pages load on demand with a shared loading fallback. Financial edits update shared in-memory sample state for the current browser session. Preferences are stored locally in the browser. Currency is fixed to INR, ordinary transactions are completed activity dated no later than today, and goal contributions are separate allocations rather than income or expense transactions.
