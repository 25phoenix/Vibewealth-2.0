# VibeWealth frontend

The frontend is a React, TypeScript, and Vite application. The current dashboard is a visual preview built with clearly labeled mock INR data; it does not connect to a backend.

## Run locally

Use Node.js 20.19+ or 22.12+ and npm. From this directory:

```sh
npm install
npm run dev
```

Vite prints the local URL after the development server starts.

## Checks

```sh
npm run typecheck
npm run lint
npm run build
```

The frontend uses CSS variables in `src/index.css` for shared design tokens, reusable shadcn/ui primitives in `src/components/ui`, and sample financial data in `src/mocks`.
