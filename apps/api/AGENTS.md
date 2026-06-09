# apps/api — Continuum agent backend

FastAPI · Python 3.12 · uv · SQLModel · Alembic · pydantic-settings · azure-identity. Package: `continuum_api` (src layout); Turbo shim name `@continuum/api`. This will host the Microsoft Agent Framework agent loop + Foundry IQ retrieval (Spec 2+). Part of a pnpm/Turborepo workspace — see the repo `README.md` and `docs/context/` for project state.

## Commands (from `apps/api` unless noted)

- Install / sync deps: `uv sync`.
- Dev server: `uv run uvicorn continuum_api.main:app --reload --port 8000` (or `pnpm --filter @continuum/api dev`, or `pnpm dev` from the repo root for web + api).
- Tests: `uv run pytest -q` (needs Postgres up and migrations applied).
- Lint: `uv run ruff check .`  ·  Format: `uv run ruff format .`. Turbo runs ruff as the api `lint` task.
- Migrations: `uv run alembic upgrade head`.

## Tooling & style

- **uv** for dependencies (not pip/poetry). **ruff** for lint + format (line length 100, rules `E`/`F`/`I`). 4-space indent.
- Type hints everywhere. Prefer explicit types, pure helpers, early returns, narrow modules. Keep files focused (under ~500 lines).
- Settings come from `continuum_api.settings.Settings` (pydantic-settings), which loads the **repo-root `.env`** (anchored via `Path(__file__).parents[4]`). `api_service_token` is REQUIRED (no default — the app fails loudly if it is unset).

## Database — two ORMs share ONE Postgres (read before any migration)

- **Drizzle (Node, `packages/db`) owns the Better Auth tables**: `user`, `session`, `account`, `verification`, `organization`, `member`, `invitation`.
- **Alembic + SQLModel (here) owns the application tables** (currently just `app_info`).
- `alembic/env.py` has an `include_object` guard restricting Alembic to `_MANAGED_TABLES`. **NEVER run `alembic revision --autogenerate`** unless every app table is in `_MANAGED_TABLES` — otherwise it emits DROP statements for the Drizzle-owned tables. When you add a SQLModel app table, add its name to `_MANAGED_TABLES` AND hand-write the migration.
- Tests build the schema from the applied migration (not `create_all`), so model and migration are forced to agree.

## API conventions

- Routers in `src/continuum_api/routes/*`, registered in `main.py`. Public health at `/health`.
- Internal endpoints the BFF calls are guarded by the `X-Service-Token` header (`require_service_token`, constant-time `secrets.compare_digest`). Reference shape: `routes/internal.py`.
- DB session via `Depends(get_session)` (`db.py`); the pool is env-tunable (`DB_POOL_SIZE` etc.).

## Verification

- After changes: `uv run ruff check .` + `uv run pytest -q`. For schema changes: hand-author the Alembic migration, `uv run alembic upgrade head`, then confirm the Better Auth tables still exist (`\dt` should show all 7 + your app tables + `alembic_version`).
