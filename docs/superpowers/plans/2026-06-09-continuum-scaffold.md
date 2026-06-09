# Continuum Scaffold (Spec 0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the full Continuum monorepo as a walking skeleton: a request flows Browser → Next.js → BFF → FastAPI → Postgres → back, with Better Auth (Microsoft) sign-in, both ORMs migrating, CI green, and Bicep infra defined.

**Architecture:** Turborepo + pnpm workspaces orchestrate the JS/TS apps; the Python FastAPI app is managed by `uv` and wired into Turbo as passthrough tasks. `apps/web` (Next.js) owns auth/UI via Better Auth + Drizzle on Postgres; `apps/api` (FastAPI) owns the domain via SQLModel + Alembic on the same Postgres (separate migration tracks, no cross-ORM FKs). The browser only talks to Next.js; a BFF route validates the Better Auth session and forwards to FastAPI.

**Tech Stack:** Turborepo, pnpm, uv, Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + TanStack (Query/Table/Form) + assistant-ui, Better Auth (Microsoft/Entra + Organization plugin) + Drizzle, FastAPI + SQLModel + Alembic + pydantic-settings, Postgres (Docker local / Azure Flexible Server), Azure Container Apps + Bicep/azd, GitHub Actions.

**Conventions for this plan:** Run all commands from the repo root `/home/skkippie/work/continuum` unless a step says otherwise. Node 20+, pnpm 9+, Python 3.12, uv installed. For pure config/scaffold tasks the "test" is a concrete build/run command with expected output (there is no unit to TDD); for logic (health endpoint, DB round-trip, BFF) we write the test first.

---

## File Structure

```
continuum/
├── package.json                 # root, pnpm workspaces, turbo scripts
├── pnpm-workspace.yaml
├── turbo.json
├── .gitignore  .nvmrc  .env.example
├── docker-compose.yml           # local Postgres
├── packages/
│   └── config/                  # shared tsconfig / eslint / prettier presets
│       ├── package.json  tsconfig.base.json  eslint.base.mjs
│   └── db/                      # Drizzle client + Better Auth schema (Node)
│       ├── package.json  drizzle.config.ts
│       └── src/{client.ts,schema.ts,index.ts}
├── apps/
│   ├── web/                     # Next.js
│   │   ├── package.json  next.config.ts  tsconfig.json  tailwind config
│   │   ├── src/lib/auth.ts           # Better Auth server
│   │   ├── src/lib/auth-client.ts    # Better Auth client
│   │   ├── src/lib/api.ts            # server-side fetch to FastAPI
│   │   ├── src/app/api/auth/[...all]/route.ts
│   │   ├── src/app/api/bff/hello/route.ts
│   │   ├── src/app/providers.tsx     # TanStack Query provider
│   │   ├── src/app/page.tsx          # health page
│   │   └── e2e/health.spec.ts        # Playwright walking-skeleton check
│   └── api/                     # FastAPI (uv)
│       ├── pyproject.toml  uv.lock  turbo-shim package.json
│       ├── alembic.ini  alembic/{env.py,versions/}
│       ├── src/continuum_api/{__init__.py,main.py,settings.py,db.py}
│       ├── src/continuum_api/models/app_info.py
│       ├── src/continuum_api/routes/{health.py,internal.py}
│       └── tests/{conftest.py,test_health.py,test_internal_hello.py}
├── infra/                       # azd + Bicep
│   ├── azure.yaml  main.bicep  main.parameters.json
│   └── modules/{postgres.bicep,storage.bicep,search.bicep,containerapps.bicep,identity.bicep}
└── .github/workflows/ci.yml
```

---

## Task 1: Initialize Turborepo + pnpm workspace root

**Files:**
- Create: `package.json`, `pnpm-workspace.yaml`, `turbo.json`, `.gitignore`, `.nvmrc`

- [ ] **Step 1: Create `.nvmrc`**

```
20
```

- [ ] **Step 2: Create `.gitignore`**

```gitignore
node_modules/
.next/
.turbo/
dist/
out/
coverage/
.env
.env.local
*.local
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
.azure/
```

- [ ] **Step 3: Create `pnpm-workspace.yaml`**

```yaml
packages:
  - "apps/*"
  - "packages/*"
```

- [ ] **Step 4: Create root `package.json`**

```json
{
  "name": "continuum",
  "private": true,
  "packageManager": "pnpm@9.12.0",
  "engines": { "node": ">=20" },
  "scripts": {
    "dev": "turbo run dev",
    "build": "turbo run build",
    "lint": "turbo run lint",
    "typecheck": "turbo run typecheck",
    "test": "turbo run test"
  },
  "devDependencies": {
    "turbo": "^2.3.0",
    "typescript": "^5.6.0"
  }
}
```

- [ ] **Step 5: Create `turbo.json`**

```json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "build": { "dependsOn": ["^build"], "outputs": [".next/**", "dist/**"] },
    "dev": { "cache": false, "persistent": true },
    "lint": {},
    "typecheck": { "dependsOn": ["^build"] },
    "test": { "dependsOn": ["^build"] }
  }
}
```

- [ ] **Step 6: Install and verify**

Run: `corepack enable && pnpm install`
Expected: pnpm resolves, creates `pnpm-lock.yaml`, no workspace errors (empty workspaces OK).

Run: `pnpm turbo --version`
Expected: prints `2.x.x`.

- [ ] **Step 7: Commit**

```bash
git add .gitignore .nvmrc pnpm-workspace.yaml package.json turbo.json pnpm-lock.yaml
git commit -m "chore: init turborepo + pnpm workspace root"
```

---

## Task 2: Shared config package

**Files:**
- Create: `packages/config/package.json`, `packages/config/tsconfig.base.json`, `packages/config/eslint.base.mjs`

- [ ] **Step 1: Create `packages/config/package.json`**

```json
{
  "name": "@continuum/config",
  "version": "0.0.0",
  "private": true,
  "files": ["tsconfig.base.json", "eslint.base.mjs"],
  "exports": {
    "./tsconfig": "./tsconfig.base.json",
    "./eslint": "./eslint.base.mjs"
  },
  "devDependencies": {
    "eslint": "^9.13.0",
    "typescript-eslint": "^8.10.0"
  }
}
```

- [ ] **Step 2: Create `packages/config/tsconfig.base.json`**

```json
{
  "$schema": "https://json.schemastore.org/tsconfig",
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "verbatimModuleSyntax": true,
    "noEmit": true
  }
}
```

- [ ] **Step 3: Create `packages/config/eslint.base.mjs`**

```javascript
import tseslint from "typescript-eslint";

export default tseslint.config(
  ...tseslint.configs.recommended,
  { ignores: ["dist/**", ".next/**", ".turbo/**"] }
);
```

- [ ] **Step 4: Verify**

Run: `pnpm install`
Expected: `@continuum/config` linked into the workspace, no errors.

- [ ] **Step 5: Commit**

```bash
git add packages/config pnpm-lock.yaml
git commit -m "chore: add shared tsconfig + eslint config package"
```

---

## Task 3: Local Postgres + env template

**Files:**
- Create: `docker-compose.yml`, `.env.example`

- [ ] **Step 1: Create `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16
    container_name: continuum-pg
    environment:
      POSTGRES_USER: continuum
      POSTGRES_PASSWORD: continuum
      POSTGRES_DB: continuum
    ports:
      - "5432:5432"
    volumes:
      - continuum_pg:/var/lib/postgresql/data
volumes:
  continuum_pg:
```

- [ ] **Step 2: Create `.env.example`**

```bash
# Shared Postgres (both Drizzle and SQLModel point here)
DATABASE_URL=postgresql://continuum:continuum@localhost:5432/continuum

# Better Auth (apps/web)
BETTER_AUTH_SECRET=replace-with-openssl-rand-base64-32
BETTER_AUTH_URL=http://localhost:3000
MICROSOFT_CLIENT_ID=
MICROSOFT_CLIENT_SECRET=
MICROSOFT_TENANT_ID=

# BFF -> FastAPI
API_BASE_URL=http://localhost:8000
SERVICE_TOKEN=dev-shared-service-token

# FastAPI (apps/api)
API_SERVICE_TOKEN=dev-shared-service-token
```

- [ ] **Step 3: Verify Postgres boots**

Run: `docker compose up -d && docker compose ps`
Expected: `continuum-pg` shows `running` / healthy on port 5432.

Run: `cp .env.example .env`
Expected: `.env` created (gitignored).

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "chore: add local postgres compose + env template"
```

---

## Task 4: Drizzle DB package + Better Auth schema generation

**Files:**
- Create: `packages/db/package.json`, `packages/db/drizzle.config.ts`, `packages/db/src/client.ts`, `packages/db/src/index.ts`
- Generated: `packages/db/src/schema.ts` (via Better Auth CLI in Task 6)

> Note: the auth tables (`user`, `session`, `account`, `verification`, `organization`, `member`, `invitation`) are generated by the Better Auth CLI in Task 6 once `auth.ts` exists. This task wires the client + config so the CLI has a target.

- [ ] **Step 1: Create `packages/db/package.json`**

```json
{
  "name": "@continuum/db",
  "version": "0.0.0",
  "private": true,
  "type": "module",
  "exports": { ".": "./src/index.ts" },
  "scripts": {
    "db:generate": "drizzle-kit generate",
    "db:migrate": "drizzle-kit migrate",
    "lint": "eslint .",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "drizzle-orm": "^0.36.0",
    "pg": "^8.13.0"
  },
  "devDependencies": {
    "@continuum/config": "workspace:*",
    "@types/pg": "^8.11.0",
    "drizzle-kit": "^0.28.0",
    "typescript": "^5.6.0"
  }
}
```

- [ ] **Step 2: Create `packages/db/tsconfig.json`**

```json
{
  "extends": "@continuum/config/tsconfig",
  "include": ["src/**/*.ts", "drizzle.config.ts"]
}
```

- [ ] **Step 3: Create `packages/db/src/client.ts`**

```typescript
import { drizzle } from "drizzle-orm/node-postgres";
import { Pool } from "pg";

const connectionString = process.env.DATABASE_URL;
if (!connectionString) throw new Error("DATABASE_URL is not set");

export const pool = new Pool({ connectionString });
export const db = drizzle(pool);
```

- [ ] **Step 4: Create `packages/db/src/index.ts`**

```typescript
export { db, pool } from "./client";
```

- [ ] **Step 5: Create `packages/db/drizzle.config.ts`**

```typescript
import { defineConfig } from "drizzle-kit";

export default defineConfig({
  dialect: "postgresql",
  schema: "./src/schema.ts",
  out: "./drizzle",
  dbCredentials: { url: process.env.DATABASE_URL! },
});
```

- [ ] **Step 6: Install + verify**

Run: `pnpm install`
Expected: `@continuum/db` deps resolve. (`drizzle-kit generate` will fail until `schema.ts` exists — that is expected; created in Task 6.)

- [ ] **Step 7: Commit**

```bash
git add packages/db pnpm-lock.yaml
git commit -m "feat(db): add drizzle client + config package"
```

---

## Task 5: Next.js app scaffold (Tailwind + shadcn + TanStack)

**Files:**
- Create: `apps/web/*` (Next.js app), `apps/web/src/app/providers.tsx`, `apps/web/tsconfig.json`, `apps/web/eslint.config.mjs`

- [ ] **Step 1: Scaffold Next.js into `apps/web`**

Run:
```bash
pnpm dlx create-next-app@latest apps/web \
  --ts --app --tailwind --eslint --src-dir --import-alias "@/*" --use-pnpm --no-turbopack
```
Expected: `apps/web` created with App Router + Tailwind. Delete the default marketing `page.tsx` content (replaced in Task 8).

- [ ] **Step 2: Add scripts + workspace deps to `apps/web/package.json`**

Merge these into the generated `apps/web/package.json`:

```json
{
  "scripts": {
    "dev": "next dev -p 3000",
    "build": "next build",
    "start": "next start -p 3000",
    "lint": "next lint",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@continuum/db": "workspace:*",
    "@tanstack/react-query": "^5.59.0",
    "@tanstack/react-table": "^8.20.0",
    "@tanstack/react-form": "^0.34.0",
    "@assistant-ui/react": "^0.7.0"
  },
  "devDependencies": {
    "@continuum/config": "workspace:*"
  }
}
```

- [ ] **Step 3: Init shadcn/ui**

Run (from repo root):
```bash
pnpm --filter web dlx shadcn@latest init -d
pnpm --filter web dlx shadcn@latest add button card
```
Expected: `apps/web/src/components/ui/{button,card}.tsx` created, `components.json` written.

- [ ] **Step 4: Create `apps/web/src/app/providers.tsx`**

```tsx
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(() => new QueryClient());
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
```

- [ ] **Step 5: Wrap the root layout with Providers**

In `apps/web/src/app/layout.tsx`, import and wrap `{children}`:

```tsx
import { Providers } from "./providers";
// ...inside <body>:
//   <Providers>{children}</Providers>
```

- [ ] **Step 6: Install + verify build**

Run: `pnpm install && pnpm --filter web build`
Expected: Next.js builds with no type errors.

- [ ] **Step 7: Commit**

```bash
git add apps/web pnpm-lock.yaml
git commit -m "feat(web): scaffold next.js + tailwind + shadcn + tanstack providers"
```

---

## Task 6: Better Auth (Microsoft + Organization) + generate Drizzle schema

**Files:**
- Create: `apps/web/src/lib/auth.ts`, `apps/web/src/lib/auth-client.ts`, `apps/web/src/app/api/auth/[...all]/route.ts`
- Generated: `packages/db/src/schema.ts`

- [ ] **Step 1: Add Better Auth deps to `apps/web/package.json`**

```json
{
  "dependencies": { "better-auth": "^1.2.0" },
  "devDependencies": { "@better-auth/cli": "^1.2.0" }
}
```
Run: `pnpm install`

- [ ] **Step 2: Create `apps/web/src/lib/auth.ts`**

```typescript
import { betterAuth } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { organization } from "better-auth/plugins";
import { db } from "@continuum/db";

export const auth = betterAuth({
  database: drizzleAdapter(db, { provider: "pg" }),
  secret: process.env.BETTER_AUTH_SECRET,
  baseURL: process.env.BETTER_AUTH_URL,
  socialProviders: {
    microsoft: {
      clientId: process.env.MICROSOFT_CLIENT_ID as string,
      clientSecret: process.env.MICROSOFT_CLIENT_SECRET as string,
      tenantId: process.env.MICROSOFT_TENANT_ID as string,
      // Graph scopes cover Work IQ (Copilot Retrieval is a Graph endpoint);
      // offline_access gives a refresh token for getAccessToken().
      scope: ["openid", "profile", "email", "offline_access", "User.Read"],
    },
  },
  plugins: [organization()],
});
```

- [ ] **Step 3: Create `apps/web/src/lib/auth-client.ts`**

```typescript
import { createAuthClient } from "better-auth/react";
import { organizationClient } from "better-auth/client/plugins";

export const authClient = createAuthClient({
  baseURL: process.env.NEXT_PUBLIC_BETTER_AUTH_URL ?? "http://localhost:3000",
  plugins: [organizationClient()],
});
```

- [ ] **Step 4: Create `apps/web/src/app/api/auth/[...all]/route.ts`**

```typescript
import { auth } from "@/lib/auth";
import { toNextJsHandler } from "better-auth/next-js";

export const { GET, POST } = toNextJsHandler(auth.handler);
```

- [ ] **Step 5: Generate the Drizzle auth schema into `packages/db`**

Run (from repo root, `.env` populated, Postgres up):
```bash
pnpm --filter web exec better-auth generate \
  --config ./src/lib/auth.ts \
  --output ../../packages/db/src/schema.ts -y
```
Expected: `packages/db/src/schema.ts` written with `user`, `session`, `account`, `verification`, `organization`, `member`, `invitation` tables. (If the CLI cannot infer the Drizzle output, generate locally then move the file to `packages/db/src/schema.ts` and fix the import path.)

- [ ] **Step 6: Generate + run the Drizzle migration**

Run:
```bash
pnpm --filter @continuum/db db:generate
pnpm --filter @continuum/db db:migrate
```
Expected: SQL migration created under `packages/db/drizzle/`, applied to Postgres. Verify:

Run: `docker compose exec postgres psql -U continuum -d continuum -c "\dt"`
Expected: lists `user`, `session`, `account`, `organization`, `member`, etc.

- [ ] **Step 7: Commit**

```bash
git add apps/web packages/db pnpm-lock.yaml
git commit -m "feat(auth): better-auth microsoft + organization, generate drizzle schema"
```

---

## Task 7: FastAPI app + settings + health endpoint (TDD)

**Files:**
- Create: `apps/api/pyproject.toml`, `apps/api/src/continuum_api/{__init__.py,main.py,settings.py}`, `apps/api/src/continuum_api/routes/health.py`, `apps/api/tests/{conftest.py,test_health.py}`

- [ ] **Step 1: Init uv project**

Run:
```bash
cd apps/api && uv init --name continuum-api --package --python 3.12 && cd ../..
```
Then set `apps/api/pyproject.toml` dependencies:

```toml
[project]
name = "continuum-api"
version = "0.0.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "sqlmodel>=0.0.22",
  "psycopg[binary]>=3.2",
  "alembic>=1.14",
  "pydantic-settings>=2.6",
  "azure-identity>=1.19",
]

[dependency-groups]
dev = ["pytest>=8.3", "httpx>=0.27", "ruff>=0.7"]

[tool.ruff]
line-length = 100

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```
Run: `cd apps/api && uv sync && cd ../..`
Expected: `.venv` created, `uv.lock` written.

- [ ] **Step 2: Write the failing test `apps/api/tests/test_health.py`**

```python
from fastapi.testclient import TestClient
from continuum_api.main import app

client = TestClient(app)

def test_health_returns_ok():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
```

- [ ] **Step 3: Run it to confirm it fails**

Run: `cd apps/api && uv run pytest tests/test_health.py -v`
Expected: FAIL — `ModuleNotFoundError: continuum_api.main` (not created yet).

- [ ] **Step 4: Create `apps/api/src/continuum_api/settings.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://continuum:continuum@localhost:5432/continuum"
    api_service_token: str = "dev-shared-service-token"


settings = Settings()
```

- [ ] **Step 5: Create `apps/api/src/continuum_api/routes/health.py`**

```python
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 6: Create `apps/api/src/continuum_api/main.py`**

```python
from fastapi import FastAPI

from continuum_api.routes import health

app = FastAPI(title="Continuum API")
app.include_router(health.router)
```

- [ ] **Step 7: Create empty `apps/api/tests/conftest.py` and `apps/api/src/continuum_api/routes/__init__.py`**

```python
# conftest.py — intentionally empty for now
```
```python
# routes/__init__.py — package marker
```

- [ ] **Step 8: Run the test to confirm it passes**

Run: `cd apps/api && uv run pytest tests/test_health.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add apps/api
git commit -m "feat(api): fastapi app + settings + health endpoint"
```

---

## Task 8: SQLModel + Alembic + DB session, baseline migration with seeded AppInfo (TDD)

**Files:**
- Create: `apps/api/src/continuum_api/db.py`, `apps/api/src/continuum_api/models/{__init__.py,app_info.py}`, `apps/api/alembic.ini`, `apps/api/alembic/env.py`, `apps/api/alembic/versions/0001_baseline.py`

- [ ] **Step 1: Create `apps/api/src/continuum_api/db.py`**

```python
from collections.abc import Iterator

from sqlmodel import Session, create_engine

from continuum_api.settings import settings

# psycopg v3 driver
engine = create_engine(settings.database_url.replace("postgresql://", "postgresql+psycopg://"))


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
```

- [ ] **Step 2: Create `apps/api/src/continuum_api/models/app_info.py`**

```python
from sqlmodel import Field, SQLModel


class AppInfo(SQLModel, table=True):
    __tablename__ = "app_info"

    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(unique=True, index=True)
    value: str
```

- [ ] **Step 3: Create `apps/api/src/continuum_api/models/__init__.py`**

```python
from continuum_api.models.app_info import AppInfo

__all__ = ["AppInfo"]
```

- [ ] **Step 4: Init Alembic and configure it for SQLModel**

Run: `cd apps/api && uv run alembic init alembic && cd ../..`
Then set `apps/api/alembic.ini` `sqlalchemy.url` to empty (we set it in env.py) and replace `apps/api/alembic/env.py` with:

```python
from logging.config import fileConfig

from alembic import context
from sqlmodel import SQLModel

from continuum_api.settings import settings
import continuum_api.models  # noqa: F401  (registers tables on SQLModel.metadata)

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

url = settings.database_url.replace("postgresql://", "postgresql+psycopg://")
target_metadata = SQLModel.metadata


def run_migrations_online() -> None:
    from sqlalchemy import create_engine

    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
```

- [ ] **Step 5: Write the baseline migration `apps/api/alembic/versions/0001_baseline.py`**

```python
"""baseline: app_info with seed row"""
from alembic import op
import sqlalchemy as sa

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_info",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("key", sa.String, nullable=False, unique=True, index=True),
        sa.Column("value", sa.String, nullable=False),
    )
    op.bulk_insert(
        sa.table("app_info", sa.column("key", sa.String), sa.column("value", sa.String)),
        [{"key": "scaffold", "value": "continuum"}],
    )


def downgrade() -> None:
    op.drop_table("app_info")
```

- [ ] **Step 6: Apply the migration**

Run: `cd apps/api && uv run alembic upgrade head && cd ../..`
Expected: `app_info` table created with one seed row.

Run: `docker compose exec postgres psql -U continuum -d continuum -c "select * from app_info;"`
Expected: one row `scaffold | continuum`.

- [ ] **Step 7: Commit**

```bash
git add apps/api
git commit -m "feat(api): sqlmodel + alembic baseline with seeded app_info"
```

---

## Task 9: Internal endpoint that reads the DB (TDD)

**Files:**
- Create: `apps/api/src/continuum_api/routes/internal.py`, `apps/api/tests/test_internal_hello.py`
- Modify: `apps/api/src/continuum_api/main.py`, `apps/api/tests/conftest.py`

- [ ] **Step 1: Write the failing test `apps/api/tests/test_internal_hello.py`**

```python
from fastapi.testclient import TestClient
from continuum_api.main import app

client = TestClient(app)
HEADERS = {"X-Service-Token": "dev-shared-service-token"}


def test_internal_hello_requires_service_token():
    res = client.get("/internal/hello")
    assert res.status_code == 401


def test_internal_hello_reads_seed_from_db():
    res = client.get("/internal/hello", headers=HEADERS)
    assert res.status_code == 200
    body = res.json()
    assert body["from"] == "fastapi"
    assert body["db"] == "continuum"  # the seeded app_info value
```

- [ ] **Step 2: Make the test DB deterministic — `apps/api/tests/conftest.py`**

```python
import pytest
from sqlmodel import Session, SQLModel, select

from continuum_api.db import engine
from continuum_api.models import AppInfo


@pytest.fixture(autouse=True, scope="session")
def _ensure_seed():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        if not s.exec(select(AppInfo).where(AppInfo.key == "scaffold")).first():
            s.add(AppInfo(key="scaffold", value="continuum"))
            s.commit()
    yield
```

- [ ] **Step 3: Run the test to confirm it fails**

Run: `cd apps/api && uv run pytest tests/test_internal_hello.py -v`
Expected: FAIL — 404 (route not registered).

- [ ] **Step 4: Create `apps/api/src/continuum_api/routes/internal.py`**

```python
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlmodel import Session, select

from continuum_api.db import get_session
from continuum_api.models import AppInfo
from continuum_api.settings import settings

router = APIRouter(prefix="/internal")


def require_service_token(x_service_token: str | None = Header(default=None)) -> None:
    if x_service_token != settings.api_service_token:
        raise HTTPException(status_code=401, detail="invalid service token")


@router.get("/hello", dependencies=[Depends(require_service_token)])
def hello(session: Session = Depends(get_session)) -> dict[str, str]:
    row = session.exec(select(AppInfo).where(AppInfo.key == "scaffold")).first()
    return {"from": "fastapi", "db": row.value if row else "missing"}
```

- [ ] **Step 5: Register the router in `apps/api/src/continuum_api/main.py`**

```python
from fastapi import FastAPI

from continuum_api.routes import health, internal

app = FastAPI(title="Continuum API")
app.include_router(health.router)
app.include_router(internal.router)
```

- [ ] **Step 6: Run the test to confirm it passes**

Run: `cd apps/api && uv run pytest -v`
Expected: all PASS (health + internal hello).

- [ ] **Step 7: Commit**

```bash
git add apps/api
git commit -m "feat(api): internal /hello reads seeded app_info, service-token guarded"
```

---

## Task 10: BFF route in Next.js → FastAPI (TDD via Playwright later; logic now)

**Files:**
- Create: `apps/web/src/lib/api.ts`, `apps/web/src/app/api/bff/hello/route.ts`

- [ ] **Step 1: Create `apps/web/src/lib/api.ts`**

```typescript
const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";
const SERVICE_TOKEN = process.env.SERVICE_TOKEN ?? "dev-shared-service-token";

export async function callApi<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "X-Service-Token": SERVICE_TOKEN },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return (await res.json()) as T;
}
```

- [ ] **Step 2: Create `apps/web/src/app/api/bff/hello/route.ts`**

```typescript
import { NextResponse } from "next/server";
import { headers } from "next/headers";
import { auth } from "@/lib/auth";
import { callApi } from "@/lib/api";

export async function GET() {
  const session = await auth.api.getSession({ headers: await headers() });

  // Walking skeleton: session is optional here so the chain is demoable
  // pre-login. Spec 1+ routes will require it.
  const upstream = await callApi<{ from: string; db: string }>("/internal/hello");

  return NextResponse.json({
    from: "bff",
    authenticated: Boolean(session?.user),
    user: session?.user?.email ?? null,
    upstream,
  });
}
```

- [ ] **Step 3: Verify the chain manually**

Run (three terminals): `docker compose up -d`; `cd apps/api && uv run uvicorn continuum_api.main:app --reload`; `pnpm --filter web dev`
Then:
```bash
curl -s http://localhost:3000/api/bff/hello | python3 -m json.tool
```
Expected:
```json
{
  "from": "bff",
  "authenticated": false,
  "user": null,
  "upstream": { "from": "fastapi", "db": "continuum" }
}
```

- [ ] **Step 4: Commit**

```bash
git add apps/web
git commit -m "feat(web): BFF /api/bff/hello forwards to fastapi with service token"
```

---

## Task 11: Health page that calls the BFF (TanStack Query)

**Files:**
- Modify: `apps/web/src/app/page.tsx`

- [ ] **Step 1: Replace `apps/web/src/app/page.tsx`**

```tsx
"use client";

import { useQuery } from "@tanstack/react-query";
import { Card } from "@/components/ui/card";

type Hello = {
  from: string;
  authenticated: boolean;
  user: string | null;
  upstream: { from: string; db: string };
};

export default function Home() {
  const { data, isLoading, error } = useQuery<Hello>({
    queryKey: ["bff-hello"],
    queryFn: async () => {
      const res = await fetch("/api/bff/hello");
      if (!res.ok) throw new Error("BFF failed");
      return res.json();
    },
  });

  return (
    <main className="mx-auto max-w-xl p-8">
      <h1 className="text-2xl font-semibold">Continuum — Walking Skeleton</h1>
      <Card className="mt-4 p-4">
        {isLoading && <p>checking chain…</p>}
        {error && <p className="text-red-600">chain broken: {String(error)}</p>}
        {data && (
          <pre className="text-sm" data-testid="chain">
            {JSON.stringify(data, null, 2)}
          </pre>
        )}
      </Card>
    </main>
  );
}
```

- [ ] **Step 2: Verify in browser**

With all three services running, open `http://localhost:3000`.
Expected: the card renders JSON showing `upstream.db: "continuum"` — proving Browser → Next → BFF → FastAPI → Postgres.

- [ ] **Step 3: Commit**

```bash
git add apps/web
git commit -m "feat(web): health page calls BFF via tanstack query"
```

---

## Task 12: Wire `apps/api` (Python) into the Turbo graph

**Files:**
- Create: `apps/api/package.json` (Turbo shim)

- [ ] **Step 1: Create `apps/api/package.json`**

```json
{
  "name": "@continuum/api",
  "private": true,
  "version": "0.0.0",
  "scripts": {
    "dev": "uv run uvicorn continuum_api.main:app --reload --port 8000",
    "lint": "uv run ruff check .",
    "typecheck": "uv run python -c \"import continuum_api.main\"",
    "test": "uv run pytest -q"
  }
}
```

- [ ] **Step 2: Verify Turbo sees it**

Run: `pnpm install && pnpm turbo run lint --filter=@continuum/api`
Expected: Turbo runs `uv run ruff check .` in `apps/api` (passes, or reports lint findings to fix).

Run: `pnpm turbo run test`
Expected: Turbo fans out — `@continuum/api` runs pytest (PASS), web/db typecheck/lint run.

- [ ] **Step 3: Commit**

```bash
git add apps/api/package.json pnpm-lock.yaml
git commit -m "chore: wire python api into turbo as passthrough tasks"
```

---

## Task 13: CI (GitHub Actions)

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create `.github/workflows/ci.yml`**

```yaml
name: CI
on:
  push: { branches: [main] }
  pull_request: {}

jobs:
  build:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: continuum
          POSTGRES_PASSWORD: continuum
          POSTGRES_DB: continuum
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready --health-interval 10s
          --health-timeout 5s --health-retries 5
    env:
      DATABASE_URL: postgresql://continuum:continuum@localhost:5432/continuum
      API_SERVICE_TOKEN: dev-shared-service-token
      SERVICE_TOKEN: dev-shared-service-token
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with: { node-version: 20, cache: pnpm }
      - uses: astral-sh/setup-uv@v3
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pnpm install --frozen-lockfile
      - run: (cd apps/api && uv sync)
      - run: (cd apps/api && uv run alembic upgrade head)
      - run: pnpm turbo run lint typecheck test build
```

- [ ] **Step 2: Verify locally (act-free)**

Run: `pnpm turbo run lint typecheck test build`
Expected: all tasks pass against the local Postgres (mirrors what CI runs).

- [ ] **Step 3: Commit + push**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: turbo lint/typecheck/test/build + python alembic on postgres service"
git push
```
Expected: GitHub Actions run goes green on the pushed branch.

---

## Task 14: Infra as code (azd + Bicep)

**Files:**
- Create: `infra/azure.yaml`, `infra/main.bicep`, `infra/main.parameters.json`, `infra/modules/{postgres,storage,search,containerapps,identity}.bicep`

> These provision the cloud targets the walking skeleton runs on. They are not executed by CI; they are run by the operator via `azd up`. Keep them deployable but minimal.

- [ ] **Step 1: Create `infra/azure.yaml`**

```yaml
name: continuum
services:
  web:
    project: ../apps/web
    language: ts
    host: containerapp
  api:
    project: ../apps/api
    language: py
    host: containerapp
```

- [ ] **Step 2: Create `infra/main.bicep`**

```bicep
targetScope = 'resourceGroup'

@minLength(3)
param environmentName string
param location string = resourceGroup().location

module identity 'modules/identity.bicep' = {
  name: 'identity'
  params: { environmentName: environmentName, location: location }
}

module postgres 'modules/postgres.bicep' = {
  name: 'postgres'
  params: { environmentName: environmentName, location: location }
}

module storage 'modules/storage.bicep' = {
  name: 'storage'
  params: { environmentName: environmentName, location: location }
}

module search 'modules/search.bicep' = {
  name: 'search'
  params: { environmentName: environmentName, location: location }
}

module apps 'modules/containerapps.bicep' = {
  name: 'containerapps'
  params: {
    environmentName: environmentName
    location: location
    managedIdentityId: identity.outputs.identityId
  }
}

output AZURE_SEARCH_ENDPOINT string = search.outputs.endpoint
output AZURE_STORAGE_ACCOUNT string = storage.outputs.accountName
output POSTGRES_HOST string = postgres.outputs.host
```

- [ ] **Step 3: Create `infra/modules/identity.bicep`**

```bicep
param environmentName string
param location string

resource uami 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${environmentName}'
  location: location
}

output identityId string = uami.id
output principalId string = uami.properties.principalId
```

- [ ] **Step 4: Create `infra/modules/postgres.bicep`**

```bicep
param environmentName string
param location string

resource pg 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: 'pg-${environmentName}'
  location: location
  sku: { name: 'Standard_B1ms', tier: 'Burstable' }
  properties: {
    version: '16'
    administratorLogin: 'continuum'
    administratorLoginPassword: 'ChangeMe-${uniqueString(resourceGroup().id)}!'
    storage: { storageSizeGB: 32 }
    highAvailability: { mode: 'Disabled' }
  }
}

resource db 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: pg
  name: 'continuum'
}

output host string = pg.properties.fullyQualifiedDomainName
```

- [ ] **Step 5: Create `infra/modules/storage.bicep`**

```bicep
param environmentName string
param location string

resource sa 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: toLower('st${environmentName}${uniqueString(resourceGroup().id)}')
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: { allowBlobPublicAccess: false }
}

output accountName string = sa.name
```

- [ ] **Step 6: Create `infra/modules/search.bicep`**

```bicep
param environmentName string
param location string

// Azure AI Search is the Foundry IQ backing resource (knowledge bases / agentic retrieval).
resource search 'Microsoft.Search/searchServices@2024-06-01-preview' = {
  name: toLower('srch-${environmentName}-${uniqueString(resourceGroup().id)}')
  location: location
  sku: { name: 'basic' }
  properties: {
    replicaCount: 1
    partitionCount: 1
    semanticSearch: 'free'
  }
}

output endpoint string = 'https://${search.name}.search.windows.net'
```

- [ ] **Step 7: Create `infra/modules/containerapps.bicep`**

```bicep
param environmentName string
param location string
param managedIdentityId string

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${environmentName}'
  location: location
  properties: {}
}

// Placeholder apps; azd injects the built images on `azd up`.
output environmentId string = env.id
output managedIdentityId string = managedIdentityId
```

- [ ] **Step 8: Create `infra/main.parameters.json`**

```json
{
  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {
    "environmentName": { "value": "${AZURE_ENV_NAME}" },
    "location": { "value": "${AZURE_LOCATION}" }
  }
}
```

- [ ] **Step 9: Validate Bicep compiles**

Run: `az bicep build --file infra/main.bicep`
Expected: compiles to ARM JSON with no errors (warnings about preview API versions are acceptable).

- [ ] **Step 10: Commit**

```bash
git add infra
git commit -m "infra: azd + bicep for postgres, storage, ai search, container apps, identity"
```

---

## Task 15: Walking-skeleton E2E (Playwright) + README runbook

**Files:**
- Create: `apps/web/playwright.config.ts`, `apps/web/e2e/health.spec.ts`
- Modify: `README.md`

- [ ] **Step 1: Add Playwright to `apps/web`**

Run: `pnpm --filter web add -D @playwright/test && pnpm --filter web exec playwright install --with-deps chromium`

- [ ] **Step 2: Create `apps/web/playwright.config.ts`**

```typescript
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://localhost:3000" },
});
```

- [ ] **Step 3: Write `apps/web/e2e/health.spec.ts`**

```typescript
import { test, expect } from "@playwright/test";

test("walking skeleton renders the full chain", async ({ page }) => {
  await page.goto("/");
  const chain = page.getByTestId("chain");
  await expect(chain).toContainText('"from": "bff"');
  await expect(chain).toContainText('"from": "fastapi"');
  await expect(chain).toContainText('"db": "continuum"');
});
```

- [ ] **Step 4: Run it (all services up)**

Run: `pnpm --filter web exec playwright test`
Expected: 1 passed — confirms Browser → Next → BFF → FastAPI → Postgres end to end.

- [ ] **Step 5: Write the runbook into `README.md`**

```markdown
# Continuum

AI-powered workforce continuity. See `docs/superpowers/specs/` for designs.

## Local dev
1. `cp .env.example .env` and fill Microsoft Entra values.
2. `docker compose up -d`            # Postgres
3. `pnpm install && (cd apps/api && uv sync)`
4. `pnpm --filter @continuum/db db:migrate`   # auth/org tables
5. `(cd apps/api && uv run alembic upgrade head)`  # domain tables
6. `pnpm dev`                        # turbo runs web + api
7. Open http://localhost:3000 — the health card proves the full chain.

## Layout
`apps/web` Next.js+BetterAuth · `apps/api` FastAPI+SQLModel · `packages/db` Drizzle · `infra/` Bicep.
```

- [ ] **Step 6: Commit**

```bash
git add apps/web README.md pnpm-lock.yaml
git commit -m "test(web): playwright walking-skeleton e2e + dev runbook"
```

---

## Definition of Done

- `pnpm dev` brings up web + api; `http://localhost:3000` renders the chain JSON with `db: "continuum"`.
- `pnpm turbo run lint typecheck test build` passes (JS + Python).
- Better Auth tables (Drizzle) and `app_info` (Alembic) both exist in Postgres via their own migration tracks.
- Microsoft sign-in route exists at `/api/auth/*` (live sign-in requires real Entra app credentials in `.env`).
- `az bicep build infra/main.bicep` compiles; `azd up` is the deploy path.
- CI is green on push.

## Notes for the implementer

- **Entra app registration is a manual prerequisite** for live Microsoft sign-in: register an app, add a web redirect `http://localhost:3000/api/auth/callback/microsoft`, create a client secret, set tenant to your Copilot-licensed tenant, and put the values in `.env`. The walking skeleton itself runs without sign-in (BFF treats session as optional).
- **Version pins** above reflect known-good majors as of 2026-06; if a package's latest differs, prefer the latest stable and adjust. Better Auth's CLI schema-generation flags can shift between minors — if `better-auth generate` flags differ, run `better-auth --help` and adapt Step 5 of Task 6.
- **Do not** add Foundry IQ / Agent Framework code here — that is Spec 1+. This task only provisions the Azure AI Search resource they will use.
