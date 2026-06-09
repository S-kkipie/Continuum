# Spec 1 Handoff — Capture Loop

The immediate next work. Full design: `docs/superpowers/specs/2026-06-09-continuum-spec1-capture-design.md`. This file is the quick orientation for a fresh context.

## Goal

Build the "how it knows" half of the loop: ingest a small organizational document set for a **Role** → produce a queryable **Successor** backed by a **Foundry IQ knowledge base**. When done, an agent (Spec 2) can query that knowledge base and get grounded answers with citations.

## Domain model (SQLModel, in `apps/api` — remember to add each table to `_MANAGED_TABLES`)

`Role` → `Successor` (1:1, maps to a Foundry IQ knowledge base) → `KnowledgeSource` (one Blob source in v1) → `Document` (n). `IngestionJob` tracks ingestion runs. `org_id` / `user_id` reference Better Auth tables — **no cross-ORM FK**; validate ownership at the BFF.

## Key design points

- **Ingestion = Foundry IQ native cracking**: drop documents in Azure Blob → Azure AI Search cracks/chunks/embeds. Least custom code, most Azure-native.
- **`FoundryKnowledge` is THE swappable interface** that Spec 2's mentor depends on: `ensure_knowledge_base`, `ensure_blob_source`, `start_indexing`, `indexing_status`, `retrieve`. Real implementation uses `azure-search-documents` + the Knowledge Bases/Retrieval REST API `2026-04-01` (GA); auth via managed identity (`DefaultAzureCredential`). Provisioning is idempotent by name (`kb-{org_id}-{role_id}`). Ship a fake implementation for tests + a shared contract test.
- Blob-only source in v1 (skip the preview SharePoint-remote/web/MCP sources). No per-user ACL trimming (managed identity over seeded data).

## Prereqs to confirm before **Phase 3** (not needed for Spec 1)

- A Copilot-licensed M365 tenant (Work IQ) and Fabric capacity (Fabric IQ). If absent, Phase 3 degrades to a believable mock and the IQ story leans on Foundry IQ (fully GA).

## Where to start

1. Plan Spec 1 with the writing-plans skill from the spec doc.
2. Add the SQLModel domain tables + `_MANAGED_TABLES` entries + a hand-written Alembic migration.
3. Build `BlobStore`, `FoundryKnowledge` (real impl behind the interface + a fake for tests), and `IngestionService`.
4. FastAPI endpoints per the spec. Acceptance: upload docs → ingest → `retrieve(query)` returns ≥1 grounded snippet with a citation; `Successor.status = ready`.

## Stack reminders (see STATE.md)

Python side: uv + ruff + SQLModel + Alembic; never `alembic --autogenerate` without updating `_MANAGED_TABLES`. New Azure SDKs land here (`azure-search-documents`, `azure-ai-projects` 1.x stable, `agent-framework`). Agent backend reaches Azure resources via managed identity; Graph-family calls (Work IQ) use the Better-Auth-issued user token forwarded through the BFF.
