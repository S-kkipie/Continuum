# Continuum — Master Overview Design

**Date:** 2026-06-09
**Status:** Approved (architecture + stack); per-phase specs in progress
**Context:** Hackathon build, production-grade code. Optimize for speed + a stage-ready demo, but write real, swappable architecture (no corners painted).

---

## 1. Vision

Continuum is an AI-powered workforce continuity platform. It continuously captures
institutional knowledge (documents, collaboration history, meetings, workflows,
business context) and turns each role into a **living AI successor**. When a new
employee joins, that successor becomes a personalized AI mentor: it builds an adaptive
onboarding plan, answers contextual "why do we do this" questions, generates practical
exercises, and tracks the employee to productivity.

**Outcome goals:** cut onboarding time, preserve knowledge through turnover, turn years
of employee experience into a durable organizational asset.

## 2. Goals & Non-Goals (hackathon scope)

**Goals**
- Demonstrate the full loop end-to-end ("both thin"): **capture → successor → mentor**.
- Real Microsoft IQ integration where it is GA and reliable (Foundry IQ core).
- Production-grade structure: clean boundaries, swappable retrieval, multi-tenant-ready.

**Non-Goals (for the hackathon)**
- No live source connectors (Teams/SharePoint sync) — seeded/uploaded docs only.
- No per-user ACL trimming in v1 — backend uses managed identity over seeded data.
- No billing, no admin RBAC beyond Better Auth defaults.
- Phase 3 (Work IQ + Fabric IQ) is "wow insurance," not critical path — degrades to mock.

## 3. Locked Stack

| Concern | Choice | Status |
|---|---|---|
| Frontend | Next.js (App Router) + TypeScript + Tailwind + **shadcn/ui** | — |
| Frontend state/data | **TanStack Query + TanStack Table + TanStack Form** | — |
| Chat UI ↔ agent | **assistant-ui** (transport-agnostic, custom FastAPI SSE) | — |
| Auth + multi-tenant | **Better Auth** (Microsoft/Entra provider + Organization plugin) | — |
| Node-side ORM | **Drizzle** (Better Auth adapter) | — |
| Agent backend | **Python + FastAPI** | — |
| Agent SDK | **Microsoft Agent Framework** (`pip install agent-framework`) | GA |
| Agent runtime | **Azure AI Foundry Agent Service** (`azure-ai-projects` 1.x stable) | GA |
| Knowledge / retrieval | **Foundry IQ** knowledge base, `azure-search-documents`, REST `2026-04-01`, Blob source | Core GA |
| Python-side ORM | **SQLModel** (+ Alembic) | — |
| App database | **Azure Database for PostgreSQL Flexible Server** (pgvector enabled) | GA |
| Doc ingestion | **Foundry IQ native cracking** (Blob → Azure AI Search cracks/chunks/embeds) | — |
| Work IQ (Phase 3) | **M365 Copilot Retrieval API** (Microsoft Graph endpoint, delegated) | GA |
| Fabric IQ (Phase 3) | **Fabric Data agent** mounted as a tool | mature |
| Backend host | **Azure Container Apps** + managed identity | GA |
| Frontend host | **Container Apps** (Next SSR) or Static Web Apps | GA |

**Do NOT bet on (too new / preview):** Fabric IQ Ontology/NL2Ontology, the broader
Work IQ pro-code API beyond Retrieval, Foundry IQ web/MCP/SharePoint-remote sources,
`azure-ai-projects` v2 beta, new builds on Semantic Kernel/AutoGen (maintenance mode).

## 4. Architecture

```
Browser
  └─ Next.js (App Router)
       ├─ Better Auth: Microsoft sign-in, session, Organization (org/member), MS token store (Drizzle → Postgres)
       ├─ shadcn/ui + TanStack (Query/Table/Form)
       └─ assistant-ui chat
            │
            ▼ (BFF: validate session, getAccessToken(microsoft), attach {userId, orgId, role})
       Next.js API route (BFF)
            │
            ▼ trusted call
  Python / FastAPI agent backend (Container Apps, managed identity)
       ├─ Microsoft Agent Framework (agent loop)
       ├─ SQLModel domain (Postgres): Role, Successor, KnowledgeSource, Document, IngestionJob, OnboardingPlan, Exercise, Progress
       ├─ Foundry IQ  → managed identity → Azure AI Search knowledge base (retrieval, GA)
       ├─ Work IQ     → Microsoft Graph / Copilot Retrieval API with delegated graphToken  [Phase 3]
       └─ Fabric IQ   → Fabric Data agent as a tool                                          [Phase 3]
```

**Auth topology (BFF pattern).** The browser talks only to Next.js. Better Auth owns
sign-in, session, and the org/role model, and stores the Microsoft tokens. A Next.js API
route validates the session, calls `getAccessToken({providerId:"microsoft"})` for a fresh
Graph token, and forwards `{userId, orgId, role, graphToken}` to the Python backend, which
stays auth-light (trusts the BFF). Foundry IQ (Azure resource audience) is reached with the
**backend managed identity**, not a user token — Work IQ/Copilot Retrieval (Graph audience)
uses the forwarded delegated token. Set Better Auth `tenantId` to the Copilot-licensed
tenant; use `profile.oid`+`profile.tid` as the identity anchor (email is unverified/mutable).

## 5. Phased Sub-Spec Program

Each sub-spec is its own spec → plan → implementation cycle. ⭐ = critical path for the demo.

| Phase | Sub-spec | Scope | Critical? |
|---|---|---|---|
| 0 | **Spec 0 · Scaffold & infra** | Monorepo (Next.js + FastAPI), Postgres, Better Auth + Drizzle, Azure resources via `azd`/Bicep, CI, one end-to-end "hello" through every layer | ⭐ |
| 1 | **Spec 1 · Domain model + ingestion → Foundry IQ** | Org/Role/Successor/KnowledgeSource model; upload + seed docs; build per-role Foundry IQ knowledge base. "How it knows." | ⭐ |
| 2 | **Spec 2 · Grounded mentor agent** | Agent Framework loop; contextual chat + "why" Q&A grounded on Foundry IQ behind a swappable retrieval interface | ⭐ |
| 2 | **Spec 3 · Onboarding plan + exercises + progress** | Adaptive plan generation, one exercise generator, progress tracked in Postgres. "What it does." | ⭐ |
| 3 | **Spec 4 · Work IQ + Fabric IQ context** | 1–2 collaboration signals (Work IQ) + 1 business metric (Fabric IQ) woven into mentor answers. Differentiator. | — |
| 4 | **Spec 5 · Seed dataset + UI polish + demo script** | Believable sample company, scripted hero flow, stage-ready | ⭐ |

**Order:** 0 → 1 → 2 → 3, then 5. Spec 4 slots in parallel after 2; drop first if time bleeds.

## 6. Cross-Cutting Domain Model (high level)

- **Organization / Member / User** — owned by Better Auth Organization plugin (Node/Drizzle).
  Python references `org_id` / `user_id`; does not own these tables.
- **Role** — a *job role* (e.g. "Senior Backend Engineer"). Belongs to an Org. The unit a
  Successor is built for. Distinct from Better Auth's permission role (`member.role`).
- **Successor** — the living AI knowledge model for a Role; maps a Role to one Foundry IQ
  knowledge base. (1 Successor : 1 Role for v1.)
- **KnowledgeSource / Document / IngestionJob** — what feeds a Successor (Spec 1 detail).
- **OnboardingPlan / Exercise / Progress** — the mentor's output and tracking (Spec 3 detail).

Chat thread state uses **Foundry Agent Service managed threads**, not Postgres. Postgres
holds operational/product data only.

## 7. The Three-IQ Story (demo narrative)

- **Foundry IQ** — the org's captured knowledge. The reliable GA core; powers grounded answers.
- **Work IQ** — *who* knew this and *how the team actually worked* (collaboration signals).
- **Fabric IQ** — *why it matters* to the business (one metric / KPI).

**Prerequisite to verify (gates Phase 3):** a **Copilot-licensed M365 tenant** (Work IQ) and
**Fabric capacity** (Fabric IQ). If absent, Phase 3 runs on a believable mock and the IQ
story leans on Foundry IQ alone.

## 8. Demo Plan (hero flow)

1. Admin view: a Role already has a Successor built from a seeded doc set (Spec 1).
2. New hire signs in (Better Auth/Microsoft), meets their role's AI mentor.
3. Mentor presents an adaptive onboarding plan (Spec 3).
4. New hire asks "why do we do X this way?" → grounded answer with citations (Spec 2),
   enriched with "Maria led this" (Work IQ) and "it drives metric Y" (Fabric IQ) if Phase 3 is live.
5. Mentor generates an exercise; progress ticks up.

## 9. Decision Log

- **Python over .NET/TS** for the agent layer — richest Agent Framework + Azure AI docs, hackathon speed, still production-viable.
- **Better Auth over MSAL** — Organization plugin gives the multi-tenant org/role model; Copilot Retrieval is a Graph endpoint so Better Auth's MS token covers Work IQ; Foundry IQ uses managed identity anyway, so MSAL's multi-resource OBO edge is moot.
- **assistant-ui over CopilotKit** — transport-agnostic, clean fit for a Python Agent Framework backend; CopilotKit's CoAgents are LangGraph/Node-first.
- **Postgres over Cosmos; no separate vector DB** — relational FK-heavy data; retrieval lives in Foundry IQ.
- **Foundry IQ native cracking** — least code, most Azure-native ingestion.
- **Hybrid retrieval approach** — Foundry IQ (managed) behind a swappable interface; own the agent/product logic in Agent Framework.
