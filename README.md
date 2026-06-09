# Continuum

AI-powered workforce continuity. Designs in `docs/superpowers/specs/`; scaffold plan in `docs/superpowers/plans/`.

## Local dev
1. `cp .env.example .env`  — root env, read by the Python API (`apps/api`).
2. Create `apps/web/.env.local` (gitignored) with the web vars — Next.js loads env from `apps/web`, not the repo root:
   `DATABASE_URL`, `BETTER_AUTH_SECRET`, `BETTER_AUTH_URL=http://localhost:3000`, `NEXT_PUBLIC_BETTER_AUTH_URL=http://localhost:3000`, `MICROSOFT_CLIENT_ID/SECRET/TENANT_ID` (fill for real sign-in), `API_BASE_URL=http://localhost:8000`, `SERVICE_TOKEN=dev-shared-service-token`.
3. `docker compose up -d`  — Postgres.
4. `pnpm install && (cd apps/api && uv sync)`
5. `pnpm --filter @continuum/db db:migrate`  — Better Auth / org tables (Drizzle).
6. `(cd apps/api && uv run alembic upgrade head)`  — app_info / domain tables (Alembic).
7. `pnpm dev`  — Turbo runs web (:3000) + api (:8000). (Ensure port 3000 is free.)
8. Open http://localhost:3000 — the health card renders the chain JSON (BFF → FastAPI → Postgres).

## Checks
- `pnpm turbo run lint typecheck test build` — whole repo (JS + Python).
- `pnpm --filter web exec playwright test` — walking-skeleton e2e (all services up; override target with `PLAYWRIGHT_BASE_URL`).

## Layout
`apps/web` Next.js + Better Auth · `apps/api` FastAPI + SQLModel · `packages/db` Drizzle · `packages/config` shared TS config · `infra/` Bicep (azd).
