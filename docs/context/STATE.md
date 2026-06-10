# Continuum — Current State

_Last updated: 2026-06-09. Update this whenever a phase completes or a major decision changes._

## Where we are

**Spec 2 (grounded mentor agent) is COMPLETE and on `main`** (merged 2026-06-09, 14 commits). A new employee chats with the role's AI `Successor` and gets streamed, grounded, cited answers (honest "I don't know" fallback). Own bounded agent loop (`MentorAgent`) over a `ChatModel` Protocol with one `retrieve` tool; `FakeChatModel` default (CI-green, no Azure) + gated real `AzureOpenAIChatModel`. `Conversation`/`Message` persist (Alembic 0003). FastAPI **SSE** chat endpoint → BFF streams-through → minimal `/chat/[successorId]` UI with citation chips. 46 api tests pass + 3 gated Azure ITs skip. Next: **Spec 3 (onboarding)** — reuses the conversation + agent.

**Spec 1 (capture loop) is COMPLETE and on `main`** (merged 2026-06-09, 15 commits). Ingest org docs for a Role → a queryable `Successor` backed by a knowledge base; `POST /internal/successors/{id}/query` returns grounded snippets with `source_document_id`. Runs fully on `local`/`fake` backends (no Azure). Spec 2 consumes its `FoundryKnowledge.retrieve` + `Successor`.

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
- 7 Better Auth tables + `app_info` + 5 capture tables + 2 mentor tables (`conversation`, `message`) live in Postgres; both migration tracks coexist (Alembic at `0003_mentor`).
- **Capture loop (Spec 1)**: `IngestionService` state machine + swappable `BlobStore` (local/azure) & `FoundryKnowledge` (fake/foundry) chosen by `settings.blob_backend`/`knowledge_backend`. FastAPI `/internal/{roles,successors,…}` (all service-token + `X-Org-Id` guarded, with org-ownership enforced per successor — cross-org → 404). BFF proxy `bff/capture/[...path]` + `/admin` page drive/observe the loop.
- **Mentor chat (Spec 2)**: `MentorAgent` bounded loop over a `ChatModel` Protocol (`agent/`), one `retrieve` tool, citations from retrieved snippets (never model-claimed). FastAPI SSE `/internal/{successors/{id}/conversations, conversations/{id}, conversations/{id}/messages}` (org-guarded, 409 if successor not ready, cross-org 404). BFF `bff/{successors/[id]/conversations, conversations/[...path]}` streams the SSE through unbuffered; `/chat/[successorId]` UI consumes it (`lib/chat-sse.ts`) with citation chips. `chat_backend=fake` default (real = `azure_openai`).

## Known issues / gotchas

- **Port 3000** is occupied on this machine by an unrelated app (`myworkin-client`). Free it before `pnpm dev`, or run web on another port (e.g. `next dev -p 3002` + `PLAYWRIGHT_BASE_URL`).
- **Two env files**: root `.env` (Python) + `apps/web/.env.local` (Next, gitignored). Duplicated keys (`DATABASE_URL`, `SERVICE_TOKEN`, auth URLs) must match. No generator script yet.
- `@continuum/db` throws at import if `DATABASE_URL` is unset.
- Biome excludes CSS (Tailwind v4 at-rules) and the generated `packages/db/src/schema.ts` from lint/format.
- **Spec 1 facts**: `python-multipart` is a runtime dep (FastAPI `UploadFile`). The `fake` knowledge backend is a **process-wide singleton** (`knowledge/factory.py`) holding in-memory KB state across requests — tests reset it via the autouse `_reset_fake_knowledge` fixture (`reset_fake_knowledge()`); never assume a fresh fake per request. The fake does ≥4-char **prefix matching** (mimics a real search analyzer's stemming) so "deploy" matches "Deploys". `local` blob root defaults to `.data/blobs` (gitignored). The `/admin` page has no polling — fine for the synchronous `fake` backend; real Azure indexing is async and would need the `…/ingest/{job_id}` poll wired into the UI (deferred).
- **Real Foundry client (`knowledge/foundry.py`) is gated/un-runnable in CI** and built against `azure-search-documents==12.0.0`'s real surface (`SearchIndexClient`, `KnowledgeBaseRetrievalClient`); a few call shapes (`connection_string` format for managed identity, terminal `synchronization_status` values) are marked `UNVERIFIED` — confirm on the first real Azure run.
- **Spec 2 facts**: deliberate stack deviation (documented in the plan §Architecture decisions + the `spec2-architecture-decisions` memory): **own loop over a `ChatModel` Protocol, NOT Microsoft Agent Framework**; real LLM = Azure OpenAI tool-calling (`openai` pinned `>=1.54,<3`, resolves v2.41, GA streaming surface field-verified). **Minimal custom SSE chat, NOT assistant-ui** (both swappable behind the Protocol/`consumeSse` parser). `pytest-asyncio` added (`asyncio_mode=auto`) — first async tests. The SSE route persists messages INSIDE the `StreamingResponse` generator (session stays open through the stream — re-verify on a FastAPI/Starlette bump). `Conversation.user_id` is now a real Better-Auth user id (forwarded as `X-User-Id` by the chat BFF, derived server-side from the session — not client-spoofable).

## Follow-ups (not blocking)

- Wire the Playwright e2e into CI (boot services + run).
- Optional `apps/web/.env.local.example` + a setup script to de-duplicate the two env files.
- A test asserting every `SQLModel.metadata` table ∈ `_MANAGED_TABLES` (guards the autogenerate footgun; now 6 app tables).
- **From Spec 1 final review (Minor, deferred):** `create_role`/`create_successor` aren't idempotent on duplicate id/role → raw 500 (should return existing or 409). `/admin` page lacks job polling (only the synchronous `fake` path is demoable end-to-end). Real-Foundry `run_ref` is the KB name (not a per-run token) so polling an old job after a re-index returns current sync state. `apps/web/src/lib/api.ts` `SERVICE_TOKEN` has a dev fallback string (consider fail-fast in prod). Migrate `datetime.utcnow()` → `datetime.now(UTC)` repo-wide (deprecation warnings).
- **From Spec 2 final review (Minor, deferred):** real `AzureOpenAIChatModel` uses `tool_choice="auto"` — a real model could answer turn 1 WITHOUT retrieving (grounding is prompt-enforced, not loop-enforced); consider forcing the tool on the first iteration if grounding must be airtight. `message` ordering relies on `created_at` microsecond resolution (fine for 2 sequential appends; add an integer `position` column if multi-append races appear). `Conversation` has a write-only `useState` in `mentor-chat.tsx` (ref is the read source — could drop the state). Add a web test runner (vitest) — `lib/chat-sse.ts` has no unit test (build/typecheck only). `/chat` needs a logged-in session with an active org to work at runtime (BFF 401s otherwise).

## Verify the whole thing

`docker compose up -d` → `pnpm install && (cd apps/api && uv sync)` → `pnpm --filter @continuum/db db:migrate` → `(cd apps/api && uv run alembic upgrade head)` → `pnpm turbo run lint typecheck test build` (expect all green) → `pnpm --filter web exec playwright test`.
