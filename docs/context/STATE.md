# Continuum — Current State

_Last updated: 2026-06-09. Update this whenever a phase completes or a major decision changes._

## Where we are

**Spec 0 (walking skeleton) is COMPLETE and on `main`.** The full chain is verified end-to-end (browser → Next.js → BFF → FastAPI → Postgres), the Playwright e2e passes, and `pnpm turbo run lint typecheck test build` is green across the whole repo.

## Stack (locked — canonical design in `docs/superpowers/specs/2026-06-09-continuum-overview-design.md`)

- **Monorepo**: Turborepo + pnpm 10.33.2 (JS/TS) + uv 0.11 (Python). Node 20+, Python 3.12.
- **Frontend**: Next.js 16 (App Router) · React 19 · TypeScript · Tailwind v4 · shadcn (base-nova) · TanStack Query/Table/Form · assistant-ui.
- **Auth**: Better Auth (Microsoft/Entra provider + Organization plugin), Drizzle adapter. **`better-auth` + `@better-auth/cli` pinned at 1.4.22** (newer versions had a `better-call` peer conflict).
- **Backend**: FastAPI · SQLModel · Alembic · pydantic-settings · azure-identity. The agent layer (Microsoft Agent Framework) + Foundry IQ retrieval land in Spec 1/2.
- **DB**: Postgres (local via docker compose; Azure DB for PostgreSQL in prod). ONE database, TWO migration tracks — Drizzle owns auth tables, Alembic owns app tables, with an `include_object` autogenerate guard in `apps/api/alembic/env.py`.
- **Lint/format**: **Biome 2.4** (JS/TS) + **ruff** (Python). NOT ESLint. Root `pnpm check` / `pnpm fix`.
- **Infra**: Bicep + azd (`infra/`), managed-identity RBAC (blob + search roles), `@secure()` Postgres password.
- **CI**: GitHub Actions — runs BOTH migrations (Drizzle + Alembic) then `turbo run lint typecheck test build` against a Postgres service.

## What works

- Better Auth Microsoft sign-in is wired (needs real Entra creds to actually log in; the walking skeleton runs without them).
- BFF seam: `apps/web/src/app/api/bff/*` → FastAPI internal endpoints via the `X-Service-Token` header.
- 7 Better Auth tables + `app_info` live in Postgres; both migration tracks coexist.

## Known issues / gotchas

- **Port 3000** is occupied on this machine by an unrelated app (`myworkin-client`). Free it before `pnpm dev`, or run web on another port (e.g. `next dev -p 3002` + `PLAYWRIGHT_BASE_URL`).
- **Two env files**: root `.env` (Python) + `apps/web/.env.local` (Next, gitignored). Duplicated keys (`DATABASE_URL`, `SERVICE_TOKEN`, auth URLs) must match. No generator script yet.
- `@continuum/db` throws at import if `DATABASE_URL` is unset.
- Biome excludes CSS (Tailwind v4 at-rules) and the generated `packages/db/src/schema.ts` from lint/format.

## Follow-ups (not blocking)

- Wire the Playwright e2e into CI (boot services + run).
- Optional `apps/web/.env.local.example` + a setup script to de-duplicate the two env files.
- A test asserting every `SQLModel.metadata` table ∈ `_MANAGED_TABLES` (guards the autogenerate footgun as app tables grow in Spec 1).

## Verify the whole thing

`docker compose up -d` → `pnpm install && (cd apps/api && uv sync)` → `pnpm --filter @continuum/db db:migrate` → `(cd apps/api && uv run alembic upgrade head)` → `pnpm turbo run lint typecheck test build` (expect all green) → `pnpm --filter web exec playwright test`.
