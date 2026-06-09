# Spec 2 · Grounded Mentor Agent (Chat + Contextual Q&A)

**Date:** 2026-06-09
**Phase:** 2 — Mentor loop (thin). ⭐ Critical path.
**Anchor:** `2026-06-09-continuum-overview-design.md` (stack, auth topology, phase map).
**Depends on:** Spec 0 (scaffold) + **Spec 1** (the `Successor`, its Foundry IQ knowledge base, and the swappable `FoundryKnowledge` interface). Spec 2 consumes `FoundryKnowledge.retrieve(...)`; it does not build ingestion.
**Feeds:** Spec 3 (onboarding plan + exercises + progress reuse the conversation + agent), Spec 4 (Work IQ / Fabric IQ enrichment of answers).

---

## 1. Purpose

Build the "what it does" half of the loop: a new employee chats with the **AI successor** for their Role and gets grounded, contextual answers — especially "why do we do this?" — every claim cited to the organization's captured knowledge. This is the streamed chat experience that is the demo's emotional center.

When this spec is done: open a conversation for a `Successor` whose knowledge base is `ready`, ask a question answerable from the org docs, and receive a streamed answer grounded in retrieved knowledge with at least one citation to a source document — and the conversation is persisted.

## 2. Scope

**In scope**
- A **mentor agent** (Microsoft Agent Framework, Python) that answers grounded on a Successor's Foundry IQ knowledge base via a single `retrieve` tool (Spec 1's `FoundryKnowledge`).
- Conversation + message **persistence** (SQLModel/Alembic): `Conversation`, `Message`.
- A **streaming chat API** (FastAPI, SSE) that runs the agent and streams deltas + a final citations event, then persists the assistant message.
- **assistant-ui** chat in `apps/web`, wired through a BFF streaming proxy that validates the Better Auth session + org ownership.
- System prompt that frames the agent as the role's AI successor: teach *what* and *why*, ground every claim in retrieved knowledge, cite sources, say "I don't know from the org's knowledge" rather than hallucinate.

**Out of scope (deferred)**
- Onboarding plan generation, exercises, progress tracking — Spec 3.
- Work IQ collaboration signals + Fabric IQ metrics in answers — Spec 4.
- Multi-agent orchestration, voice, file upload in chat.
- Per-user ACL trimming of retrieval (managed identity over seeded data, per Spec 1).
- Editing/branching messages, regeneration history.

## 3. Domain additions (SQLModel — add to `_MANAGED_TABLES`)

```
Successor (Spec 1)
   └── Conversation (n)   — one chat thread between an employee and a Successor
         └── Message (n)  — ordered turns (user / assistant), assistant rows carry citations
```

| Entity | Key fields | Notes |
|---|---|---|
| `Conversation` | `id`, `successor_id`, `user_id`, `title`, `created_at`, `updated_at` | `user_id` references the Better Auth user (no cross-ORM FK; validated at the BFF). `title` defaults to the first user message, truncated. |
| `Message` | `id`, `conversation_id`, `role` (`user`/`assistant`), `content` (text), `citations` (JSONB, nullable), `created_at` | `citations` = `[{title, source_document_id, snippet, score}]` for assistant rows. Tool/retrieval internals are NOT persisted as separate rows in v1. |

Conversation history (the ordered `Message` rows) is rehydrated to seed the agent each turn — **we own thread state in Postgres**, not Foundry managed threads. (This refines the overview's "managed threads" note: because we run the Agent Framework loop ourselves and Spec 3 needs conversations relationally linked to the employee/role, Postgres persistence is simpler and gives us the join we need.)

## 4. Architecture & Components

Each unit has one purpose, a defined interface, explicit dependencies. The agent + retrieval live in `apps/api`; the chat UI in `apps/web`.

### 4.1 `MentorAgent` (the agent loop)
- **Does:** build and run the Agent Framework agent for a given `Successor` and stream its response over a conversation history + a new user message. The agent has exactly one tool — `retrieve` — and a system prompt framing it as the role's successor.
- **Interface:**
  - `stream(successor: Successor, history: list[Message], user_message: str) -> AsyncIterator[ChatEvent]`
  - `ChatEvent` is one of: `TextDelta(text)`, `RetrievalStarted(query)`, `Citations(list[Citation])`, `Done(finish_reason)`. (`RetrievalStarted` is a UI affordance — "searching the knowledge base…".)
- **Depends on:** `FoundryKnowledge` (Spec 1, for the `retrieve` tool), a chat model client (Azure OpenAI via Agent Framework — `agent-framework` + the Azure client; model + endpoint from settings, auth via managed identity / `DefaultAzureCredential`), and `SystemPromptBuilder`.
- **Grounding contract:** the `retrieve` tool calls `FoundryKnowledge.retrieve(kb_ref_for(successor), query, top=N)` and returns snippets; the system prompt instructs the model to answer ONLY from retrieved content and to attach citations. The `Citations` event is assembled from the retrieved snippets the model actually used (mapped back to `source_document_id`).

### 4.2 `retrieve` tool
- **Does:** the single agent tool — given a search query, return grounded snippets + citation metadata from the Successor's knowledge base.
- **Interface (tool signature exposed to the model):** `retrieve(query: str) -> list[{content, title, source_document_id, score}]`.
- **Depends on:** `FoundryKnowledge.retrieve` (Spec 1). The Successor's `knowledge_base_name` is bound when the agent is constructed.

### 4.3 `ConversationService`
- **Does:** create conversations, append messages, load ordered history, set title. Authorizes on `successor_id`'s org (via the BFF-supplied `org_id`).
- **Interface:** `create(successor_id, user_id) -> Conversation`; `history(conversation_id) -> list[Message]`; `append(conversation_id, role, content, citations=None) -> Message`.
- **Depends on:** SQLModel repositories.

### 4.4 Chat API (FastAPI, streaming)
- **Does:** accept a user message for a conversation, run `MentorAgent.stream`, relay `ChatEvent`s as Server-Sent Events, and on completion persist the user message + the assembled assistant message (with citations).
- See §5 (data flow) and §6 (API + SSE protocol).

### 4.5 Web: `MentorChat` + runtime adapter (`apps/web`)
- **Does:** render the chat with **assistant-ui** (`Thread`), backed by a custom runtime that POSTs to the BFF chat route and consumes the SSE stream, rendering streamed text + a citations footer per assistant message.
- **Depends on:** `@assistant-ui/react`, a BFF route (§4.6), TanStack Query for conversation list/load.

### 4.6 BFF chat proxy (`apps/web`)
- **Does:** `POST /api/bff/conversations/{id}/messages` — validate the Better Auth session + that the conversation's Successor belongs to the user's org, then **proxy the SSE stream** from FastAPI (attaching `X-Service-Token`, forwarding `{userId, orgId}`). The browser never calls FastAPI directly (overview §4).

## 5. Data flow

```
Employee (assistant-ui) ──POST /api/bff/conversations/{id}/messages──▶ Next BFF
  BFF: validate session + org ownership; open SSE to FastAPI with X-Service-Token + {userId, orgId}
        │
        ▼
FastAPI POST /internal/conversations/{id}/messages  (SSE)
  1. load Successor (must be status=ready) + Conversation history
  2. MentorAgent.stream(successor, history, user_message):
       - model decides to call retrieve(query)
       - retrieve → FoundryKnowledge.retrieve(kb, query) → snippets
       - model streams grounded answer (TextDelta events)
       - Citations event assembled from used snippets
  3. emit SSE: event: delta (repeated) → event: citations → event: done
  4. persist: append(user msg) ; append(assistant msg + citations)
        │
        ▼  (BFF relays the same SSE upstream)
assistant-ui renders streamed text + citation chips
```

Conversation creation is a separate, non-streaming call: `POST /api/bff/successors/{id}/conversations` → FastAPI creates a `Conversation`, returns its id.

## 6. API surface

**FastAPI (internal, service-token guarded, receive `{userId, orgId}` from BFF):**

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/internal/successors/{id}/conversations` | Create a conversation (Successor must be `ready`) → returns conversation id |
| `GET` | `/internal/conversations/{id}` | Conversation + ordered messages |
| `POST` | `/internal/conversations/{id}/messages` | **SSE** — send a user message, stream the grounded answer |

**SSE event protocol** (`text/event-stream`):
```
event: delta       data: {"text": "..."}            # repeated, token chunks
event: retrieval   data: {"query": "..."}           # optional UI affordance
event: citations   data: [{"title","source_document_id","snippet","score"}]
event: done        data: {"finish_reason": "stop"}
event: error       data: {"detail": "..."}          # on failure mid-stream
```

**BFF (Next.js):** `POST /api/bff/successors/{id}/conversations`, `GET /api/bff/conversations/{id}`, `POST /api/bff/conversations/{id}/messages` (proxies the SSE).

## 7. Error handling

- **Successor not `ready`** (knowledge base still indexing) → 409 from the conversation-create / message endpoints with a clear code; UI shows "still learning this role."
- **Retrieval returns nothing** → the agent answers "I don't have that in the org's knowledge yet" (system-prompt-enforced); `citations` is empty, not fabricated.
- **Model/agent error mid-stream** → emit `event: error`, then close; persist the user message but mark the assistant turn failed (no partial assistant row, or a row with `finish_reason=error`). BFF surfaces a retryable error to assistant-ui.
- **Foundry IQ unavailable** → typed error from the `retrieve` tool; the turn fails cleanly (502 before streaming starts, or `error` event mid-stream).
- **Auth**: BFF rejects conversations whose Successor's org ≠ the caller's org (404, not 403, to avoid leaking existence).

## 8. Testing strategy

- **Unit — `MentorAgent`** against a **fake `FoundryKnowledge`** (returns canned snippets) and a **fake/stub chat model** that deterministically calls `retrieve` then emits a templated answer. Assert: the tool is called, `Citations` map to the canned `source_document_id`s, the event sequence is `delta* → citations → done`, and empty-retrieval yields an "I don't know" answer with no citations.
- **Unit — `ConversationService`**: create/append/history ordering; title derivation.
- **API — SSE**: FastAPI `TestClient` reads the event stream for a message; assert event types/order and that messages persist (user + assistant + citations).
- **Contract**: reuse Spec 1's `FoundryKnowledge` fake so the swap point stays honest.
- **Integration (one, gated `@integration`)**: against a real Successor (Spec 1 dev resource) + a real Azure OpenAI deployment — one question returns a streamed grounded answer with a citation. Skipped without Azure creds.
- **Web**: a component test that the runtime adapter parses the SSE protocol into assistant-ui messages + citation chips (mock the BFF stream).

## 9. Acceptance criteria

1. Create a conversation for a `ready` Successor; sending a question answerable from its docs streams a grounded answer (visible token-by-token in assistant-ui).
2. The answer carries ≥1 citation mapping to a real source `Document` from Spec 1.
3. A question with no answer in the org knowledge yields an honest "not in the org's knowledge" reply with empty citations (no hallucination).
4. The conversation + its user/assistant messages (with citations) persist and reload.
5. The whole turn flows browser → BFF → FastAPI → agent → Foundry IQ retrieval → back, with the browser never calling FastAPI directly.

## 10. Open questions / risks

- **Azure OpenAI model + deployment**: pick the deployment at config time (settings: endpoint, deployment name, auth). Agent Framework's streaming + tool-calling API is GA but new — validate the streaming tool-call event shape early against the installed `agent-framework` version.
- **Two-hop streaming** (FastAPI SSE → Next BFF proxy → browser): confirm the BFF route streams (no buffering) under Next 16; verify backpressure/flush. Prototype this seam first — it's the riskiest integration.
- **Citation fidelity**: mapping the model's used snippets back to `source_document_id` — start by citing all retrieved snippets the turn used; refine to "actually referenced" later.
- **Token cost** (Foundry IQ token billing + model tokens) — keep retrieval `top` modest and reasoning effort low in dev.
- **assistant-ui runtime adapter** for a custom SSE backend — verify the current `@assistant-ui/react` runtime API; if the adapter is heavier than expected, fall back to a minimal custom chat UI that consumes the same SSE (the protocol in §6 is UI-agnostic).
