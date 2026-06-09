# Continuum

**AI-powered workforce continuity.** Continuum continuously captures institutional knowledge — documents, collaboration history, meetings, workflows, business context — and turns each role into a living **AI successor**: a personalized AI mentor that onboards new hires, answers contextual "why do we do this" questions, generates practical exercises, and guides them to productivity. Built on Microsoft IQ (Foundry IQ retrieval, Work IQ collaboration signals, Fabric IQ business context).

> **Status: Spec 0 (walking skeleton) complete.** Next: Spec 1 (capture loop). See `docs/context/` for state, roadmap, and the next-phase handoff; `docs/superpowers/` for designs and plans.

## Architecture

```
Browser
  → Next.js (Better Auth Microsoft + Org, Drizzle, shadcn/Tailwind v4, TanStack, assistant-ui)
  → BFF route (validate session, attach X-Service-Token)
  → FastAPI (Microsoft Agent Framework [Spec 2+], SQLModel, service-token guard)
       ├─ Foundry IQ (Azure AI Search) — retrieval  [Spec 1+]
       └─ Postgres — application data
```

Monorepo: **Turborepo + pnpm** (JS/TS) + **uv** (Python). One Postgres, two migration tracks — Drizzle owns the Better Auth/org tables, Alembic owns the app tables (guarded so autogenerate can't drop the other track's tables).

## Layout

- `apps/web` — Next.js 16 + Better Auth + shadcn/Tailwind v4 + TanStack. See `apps/web/AGENTS.md`.
- `apps/api` — FastAPI + SQLModel + Alembic (uv). See `apps/api/AGENTS.md`.
- `packages/db` — Drizzle client + the Better-Auth-generated schema.
- `packages/config` — shared TypeScript config base.
- `infra/` — Bicep + azd (Postgres, Storage, Azure AI Search, Container Apps, managed identity).
- `docs/superpowers/` — specs + plans · `docs/context/` — durable state / roadmap / handoff.

## Local dev

1. `cp .env.example .env`  — root env, read by the Python API (`apps/api`).
2. Create `apps/web/.env.local` (gitignored) — Next loads env from `apps/web`, not the repo root:
   `DATABASE_URL`, `BETTER_AUTH_SECRET`, `BETTER_AUTH_URL=http://localhost:3000`, `NEXT_PUBLIC_BETTER_AUTH_URL=http://localhost:3000`, `MICROSOFT_CLIENT_ID/SECRET/TENANT_ID` (fill for real sign-in), `API_BASE_URL=http://localhost:8000`, `SERVICE_TOKEN=dev-shared-service-token`.
3. `docker compose up -d`  — Postgres.
4. `pnpm install && (cd apps/api && uv sync)`
5. `pnpm --filter @continuum/db db:migrate`  — Better Auth / org tables (Drizzle).
6. `(cd apps/api && uv run alembic upgrade head)`  — app tables (Alembic).
7. `pnpm dev`  — Turbo runs web (:3000) + api (:8000). Free port 3000 first.
8. Open http://localhost:3000 — the health card renders the chain (BFF → FastAPI → Postgres).

## Checks

- `pnpm check` — Biome lint + format (JS/TS). `pnpm fix` applies safe fixes.
- `pnpm turbo run lint typecheck test build` — whole repo (Biome + ruff/pytest + web build).
- `pnpm --filter web exec playwright test` — walking-skeleton e2e (services up; `PLAYWRIGHT_BASE_URL` to override).

## Tooling

JS/TS: **Biome** (not ESLint). Python: **ruff**. Node 20+, pnpm 10, Python 3.12, uv. Each app has its own `AGENTS.md` with conventions.
