# Spec 1 · Domain Model + Ingestion → Foundry IQ (Capture Loop)

**Date:** 2026-06-09
**Phase:** 1 — Capture loop (thin). ⭐ Critical path.
**Anchor:** See `2026-06-09-continuum-overview-design.md` for stack, auth topology, and the phase map.
**Depends on:** Spec 0 (scaffold) — assumes the monorepo, FastAPI service, Postgres, Better Auth, and Azure resources exist.

---

## 1. Purpose

Build the "how it knows" half of the loop: ingest a small set of organizational documents
for a **Role** and turn them into a queryable **Successor** backed by a **Foundry IQ
knowledge base**. When this spec is done, an agent (Spec 2) can ask the knowledge base a
question and get grounded answers with citations.

## 2. Scope

**In scope**
- Domain model: `Role`, `Successor`, `KnowledgeSource`, `Document`, `IngestionJob` (SQLModel).
- Upload + seed documents into per-Successor Azure **Blob** storage.
- Provision one **Foundry IQ knowledge base** per Successor, with a **Blob-backed knowledge source**.
- Trigger ingestion (Azure AI Search native cracking/chunking/embedding) and track it.
- A `FoundryKnowledge` interface (the swappable retrieval provider) + a smoke `retrieve()` to prove grounding.
- FastAPI endpoints for the admin capture flow.

**Out of scope (deferred)**
- Live connectors / incremental sync (Teams, SharePoint) — upload + seed only.
- Per-user ACL trimming — managed identity over seeded data (Overview §4).
- Custom parsing (Document Intelligence, unstructured) — native cracking only.
- Work IQ / Fabric IQ enrichment — Spec 4.
- The mentor agent loop, onboarding plans, exercises — Spec 2 / Spec 3.
- Multiple knowledge sources per Successor — exactly one Blob source in v1.

## 3. Domain Model

```
Organization (Better Auth, Node/Drizzle)   ← referenced by org_id, not owned here
   └── Role (job role)
         └── Successor (1:1)  ── maps to ──▶  Foundry IQ knowledge base
               └── KnowledgeSource (1, type=blob)  ── maps to ──▶  Foundry IQ knowledge source
                     └── Document (n)              ── stored as ──▶  blobs in the source's container
               └── IngestionJob (n)               ── tracks a run of native cracking/indexing
```

**SQLModel entities (Python, Postgres):**

| Entity | Key fields | Notes |
|---|---|---|
| `Role` | `id`, `org_id`, `title`, `description`, `created_at` | `org_id` references Better Auth org; no FK across the Node/Python boundary, validated at the BFF. |
| `Successor` | `id`, `role_id` (unique), `knowledge_base_name`, `status` (`provisioning`/`ready`/`failed`), `summary`, `created_at` | 1:1 with Role. `knowledge_base_name` is the Foundry IQ KB identifier (deterministic, see §5). |
| `KnowledgeSource` | `id`, `successor_id`, `type` (`blob`), `container`, `status`, `created_at` | Exactly one per Successor in v1. `container` = the Blob container backing the Foundry IQ source. |
| `Document` | `id`, `source_id`, `filename`, `content_type`, `blob_path`, `size_bytes`, `status` (`uploaded`/`indexing`/`indexed`/`failed`), `error`, `created_at` | One row per uploaded file. |
| `IngestionJob` | `id`, `successor_id`, `status` (`queued`/`running`/`succeeded`/`partial`/`failed`), `doc_total`, `doc_indexed`, `doc_failed`, `started_at`, `finished_at`, `error` | Tracks one indexing run. |

**Naming caution:** domain `Role` (job role) is distinct from Better Auth's permission
`member.role`. Keep them separate; never join across the boundary in SQL.

## 4. Architecture & Components

Each unit has one purpose, a defined interface, and explicit dependencies.

### 4.1 `BlobStore`
- **Does:** create per-Successor container, upload a document, list/delete blobs.
- **Interface:** `ensure_container(successor_id) -> container`; `put(container, filename, bytes, content_type) -> blob_path`; `list(container)`; `delete(container, blob_path)`.
- **Depends on:** `azure-storage-blob`, managed identity (`DefaultAzureCredential`).

### 4.2 `FoundryKnowledge` (the swappable retrieval provider)
- **Does:** provision a knowledge base + Blob knowledge source, trigger/refresh indexing, report status, and `retrieve(query)` for the smoke test. **This is the interface Spec 2's mentor depends on** — implementations are swappable (real Foundry IQ vs a fake for tests vs the managed-agent path).
- **Interface:**
  - `ensure_knowledge_base(name) -> kb_ref`
  - `ensure_blob_source(kb_ref, container) -> source_ref`
  - `start_indexing(kb_ref) -> run_ref`
  - `indexing_status(run_ref) -> {state, indexed, failed, errors}`
  - `retrieve(kb_ref, query, *, top=5) -> [{content, citation, score}]`
- **Implementation:** `azure-search-documents` + Knowledge Bases/Sources/Retrieval REST `2026-04-01`; auth via managed identity. Provisioning is **idempotent by name**.
- **Depends on:** Azure AI Search service (the Foundry IQ backing resource), managed identity.

### 4.3 `IngestionService`
- **Does:** orchestrate the capture flow — ensure container + KB + source, persist `Document` rows, kick `start_indexing`, create/track an `IngestionJob`, reconcile per-document status from `indexing_status`, set `Successor.status`.
- **Interface:** `add_documents(successor_id, files)`, `ingest(successor_id) -> job_id`, `sync_job(job_id) -> IngestionJob`.
- **Depends on:** `BlobStore`, `FoundryKnowledge`, repositories.

### 4.4 Repositories
- SQLModel repositories per entity (`RoleRepo`, `SuccessorRepo`, `KnowledgeSourceRepo`, `DocumentRepo`, `IngestionJobRepo`). Thin CRUD; no business logic.

## 5. Foundry IQ Mapping & Conventions

- One **knowledge base** per Successor. Deterministic name: `kb-{org_id}-{role_id}` (idempotent provisioning, no duplicates on retry).
- One **knowledge source** of type Blob per KB, pointing at the Successor's container (`continuum-{successor_id}`).
- Documents = blobs in that container; **Azure AI Search native cracking** chunks + embeds (no custom parser).
- REST api-version **`2026-04-01`** (GA) for production-shaped code; avoid preview-only source types (web/MCP/SharePoint-remote).
- Billing is token-based — keep reasoning-effort modest on `retrieve` during dev.

## 6. Data Flow

```
Admin (Next.js) ──BFF──▶ FastAPI
  1. POST /roles                         → create Role
  2. POST /roles/{id}/successor          → create Successor; FoundryKnowledge.ensure_knowledge_base; status=provisioning
  3. POST /successors/{id}/documents     → BlobStore.put each file; Document rows (status=uploaded)
  4. POST /successors/{id}/ingest        → ensure_blob_source; start_indexing; IngestionJob(queued→running); docs→indexing
  5. (poll) GET /successors/{id}/ingest/{jobId} → sync_job: indexing_status → reconcile docs; job succeeded/partial/failed; Successor.status=ready
  6. (smoke) POST /successors/{id}/query → FoundryKnowledge.retrieve → grounded snippets + citations  (proves §10 acceptance)
```

Ingestion runs async (background task / Container Apps job). The UI polls the job endpoint
(TanStack Query) until terminal.

## 7. API Surface (FastAPI)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/orgs/{orgId}/roles` | Create a Role |
| `GET` | `/orgs/{orgId}/roles` | List Roles |
| `POST` | `/roles/{roleId}/successor` | Create Successor (provision KB) |
| `GET` | `/successors/{id}` | Successor status + doc counts |
| `POST` | `/successors/{id}/documents` | Upload documents (multipart) |
| `POST` | `/successors/{id}/ingest` | Start ingestion → returns `jobId` |
| `GET` | `/successors/{id}/ingest/{jobId}` | Ingestion job status |
| `POST` | `/successors/{id}/query` | Smoke retrieval (dev/demo proof) |

All routes receive `{userId, orgId, role}` from the BFF and authorize on `orgId` ownership.

## 8. Error Handling

- **Provisioning** is idempotent by name → safe to retry; surface `failed` on Successor with the error.
- **Per-document failures** captured on the `Document` row (`status=failed`, `error`); a run with some failures ends `partial`, not `failed`.
- **Indexing not yet complete** → job stays `running`; poll is safe and non-mutating.
- **Blob upload failures** → reject the upload, no `Document` row created.
- **Foundry IQ unavailable** → `ensure_*` raises a typed `FoundryError`; service marks Successor `failed`, logs, returns 502 to the BFF.

## 9. Testing Strategy

- **Unit:** `IngestionService` against a **fake `FoundryKnowledge`** and a fake `BlobStore` — verify state machine (uploaded → indexing → indexed/partial/failed) and `Successor.status` transitions.
- **Contract:** the `FoundryKnowledge` interface has a shared test suite both the real and fake implementations pass (protects the swap point Spec 2 relies on).
- **Integration (one, gated):** push a single small doc through the real Foundry IQ dev resource → `start_indexing` → poll until indexed → `retrieve` returns a citation. Tagged `@integration`, skipped without Azure creds.
- **API:** FastAPI `TestClient` over the endpoints with the service faked.

## 10. Acceptance Criteria

1. Create a Role + Successor → a Foundry IQ knowledge base exists (idempotent on retry).
2. Upload N (≈5–10) seed documents → `Document` rows in `uploaded`.
3. Trigger ingestion → job reaches `succeeded` (or `partial` with per-doc errors surfaced); `Successor.status=ready`.
4. `POST /successors/{id}/query` with a question answerable from the docs → returns ≥1 grounded snippet **with a citation** to a source document.
5. The whole flow is observable from the admin UI (TanStack Query polling) — this is the demoable "how it knows."

## 11. Open Questions / Risks

- **Foundry IQ preview surface in portal vs GA REST** — build against REST `2026-04-01`, not portal click-ops, to stay production-shaped.
- **Indexing latency** for the demo — measure on the seed set; if slow, pre-warm Successors before the live demo.
- **Free-tier limits** on Azure AI Search (doc count / token allowance) — keep the seed set small.
- **Container-per-Successor** Blob layout — confirm naming limits; fall back to prefix-per-Successor in one shared container if needed.
