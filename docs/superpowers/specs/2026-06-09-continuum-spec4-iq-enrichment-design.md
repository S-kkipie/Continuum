# Spec 4 · Work IQ + Fabric IQ Enrichment

**Date:** 2026-06-09
**Phase:** 3 — Differentiator (not critical path). Degrades gracefully to mock.
**Anchor:** `2026-06-09-continuum-overview-design.md` (stack, auth topology, three-IQ story §7).
**Depends on:** Spec 2 (`MentorAgent.stream`, `Message.citations`, `Conversation`/`Message` persistence, BFF chat proxy).
**Feeds:** Spec 5 (seed dataset + demo polish — the enriched "Maria led this" + metric moment).

---

## 1. Purpose

Enrich the mentor's grounded answers with two additional IQ signals that make the demo
differentiated:

- **Work IQ** — *who* knew this and *how the team actually handled it*: 1–2 collaboration
  signals surfaced via the **M365 Copilot Retrieval API** (a Graph endpoint) using the
  delegated Graph token the BFF already holds. Adds the "Maria led this project" layer.
- **Fabric IQ** — *why it matters* to the business: one quantified metric from a
  **Fabric Data agent** mounted as a tool. Adds the "it drives metric Y" layer.

Foundry IQ (Spec 2) remains the grounding core. This spec adds enrichment alongside it —
never replacing it. Both enrichment providers are **swappable and mockable by default**: the
demo runs with zero Azure/M365 prerequisites; real clients activate by config + the
forwarded Graph token.

## 2. Scope

### In scope

- `WorkIQ` Protocol + `MockWorkIQ` (canned signals, default) + `CopilotRetrievalWorkIQ`
  (real, Copilot Retrieval API over forwarded Graph token).
- `FabricIQ` Protocol + `MockFabricIQ` (canned metric, default) + `FabricDataAgentClient`
  (real, Fabric Data agent as tool).
- Wiring both providers into `MentorAgent` as additional agent tools (parallel to the
  existing `retrieve` tool) — or as a post-retrieval enrichment step — see §5.4.
- Persisting enrichment signals alongside `Message.citations` (no new table — JSONB
  extension, see §4).
- BFF forwarding the Graph token from Better Auth to FastAPI for Work IQ.
- A settings-driven factory (`IQClientFactory`) that returns mock or real implementations.

### Out of scope

- The broader Work IQ pro-code API (preview, thin docs) — anchored on GA Retrieval API only.
- Fabric IQ Ontology / NL2Ontology (preview) — Fabric Data agent only.
- Onboarding plan or exercise enrichment — Spec 3.
- Demo seed data and script — Spec 5.
- Per-user ACL trimming on Work IQ results (delegated token scope is sufficient for v1).

## 3. Prerequisites & Access

### 3.1 Work IQ — M365 Copilot Retrieval API

- **What it is:** a Microsoft Graph endpoint (`graph.microsoft.com`) that queries
  enterprise content indexed by Copilot. GA as of the GA Retrieval API surface.
- **Auth:** delegated Graph token — exactly the token Better Auth already issues (Microsoft
  provider, `offline_access` scope). The BFF calls
  `auth.api.getAccessToken({providerId: "microsoft"})` and forwards it in
  `X-Graph-Token: <token>` to FastAPI. No OBO, no separate credential.
- **Tenant prerequisite:** a **Copilot-licensed M365 tenant**. Without one, the real client
  will return 403/empty; the factory falls back to `MockWorkIQ`.
- **Scope required:** `Copilot.Chat.Read` or equivalent Retrieval API delegated scope (verify
  on target tenant; add to Better Auth's `scope` list in `auth.ts`).
- **Graph endpoint:** `POST https://graph.microsoft.com/v1.0/copilot/retrieval` (GA surface).

### 3.2 Fabric IQ — Fabric Data Agent

- **What it is:** a Fabric Data agent configured to answer business metric queries against a
  Fabric lakehouse/warehouse. Consumed as a tool call (HTTP endpoint or Azure AI
  Agent-compatible tool registration).
- **Auth:** the FastAPI backend calls the Fabric Data agent using managed identity or an API
  key configured at deploy time. The user's Graph token is NOT required for Fabric IQ.
- **Capacity prerequisite:** **Azure Fabric capacity** (F-SKU) with a Data agent provisioned
  and accessible from the Container Apps outbound IP. Without it, the factory returns
  `MockFabricIQ`.
- **No preview dependency:** the Fabric IQ Ontology/NL2Ontology API is explicitly NOT used.

### 3.3 Mock fallback (the default)

Both providers default to their `Mock` implementations. The demo is fully runnable
with no Copilot tenant and no Fabric capacity. Switching to real requires:

```toml
# apps/api/settings.toml (or env)
[iq]
work_iq_backend = "copilot"   # "mock" | "copilot"
fabric_iq_backend = "fabric"  # "mock" | "fabric"

# When work_iq_backend = "copilot"
# Graph token must arrive from BFF on every mentor request

# When fabric_iq_backend = "fabric"
fabric_agent_endpoint = "https://<fabric-agent-host>/..."
fabric_agent_api_key = "<secret>"   # or managed identity
```

## 4. Domain Additions

No new SQLModel tables are introduced. The existing `Message.citations` JSONB field
(Spec 2) is extended to carry enrichment signals alongside Foundry citations.

### 4.1 Extended `citations` schema (per-assistant `Message`)

```python
# Existing (Spec 2) — Foundry citation item:
class FoundryCitation(TypedDict):
    title: str
    source_document_id: str
    snippet: str
    score: float

# New — Work IQ signal item:
class CollaborationSignal(TypedDict):
    kind: Literal["collaboration_signal"]
    summary: str          # "Maria led this — see Q3 design review"
    actor: str            # display name, e.g. "Maria G."
    resource_url: str     # MS Graph driveItem/message URL (or "" for mock)
    relevance_score: float

# New — Fabric IQ metric item:
class BusinessMetric(TypedDict):
    kind: Literal["business_metric"]
    label: str            # "Customer onboarding time"
    value: str            # "14 days avg (Q1 2025)"
    direction: Literal["up", "down", "neutral"]
    context: str          # "Reduced 22 % after this process was standardised"
    source: str           # "Fabric: continuum_metrics.onboarding_kpis" (or "mock")

# Message.citations is List[FoundryCitation | CollaborationSignal | BusinessMetric]
# Discriminated on the `kind` field; FoundryCitation has no `kind` for back-compat
# (treat absence of `kind` as "foundry_citation").
```

`_MANAGED_TABLES` guard is unchanged — no new Alembic table; only the JSONB structure widens.

## 5. Architecture & Components

### 5.1 `WorkIQ` Protocol

```python
# apps/api/continuum/iq/work_iq.py

from typing import Protocol, runtime_checkable
from continuum.iq.types import CollaborationSignal

@runtime_checkable
class WorkIQ(Protocol):
    async def signals(
        self,
        query: str,
        context: str,
        *,
        graph_token: str,
        top: int = 2,
    ) -> list[CollaborationSignal]:
        """
        Return up to `top` collaboration signals relevant to `query`/`context`.
        `graph_token` is the delegated Graph token forwarded by the BFF.
        Returns [] on any failure — never raises.
        """
        ...
```

**`MockWorkIQ`** (default, no network):

```python
class MockWorkIQ:
    _SIGNALS: list[CollaborationSignal] = [
        {
            "kind": "collaboration_signal",
            "summary": "Maria G. led this initiative — drove the Q3 architecture review",
            "actor": "Maria G.",
            "resource_url": "",
            "relevance_score": 0.91,
        },
        {
            "kind": "collaboration_signal",
            "summary": "The eng team resolved a similar trade-off in the 2024 platform migration",
            "actor": "Eng Team",
            "resource_url": "",
            "relevance_score": 0.78,
        },
    ]

    async def signals(self, query, context, *, graph_token, top=2):
        return self._SIGNALS[:top]
```

**`CopilotRetrievalWorkIQ`** (real, gated by config):

```python
class CopilotRetrievalWorkIQ:
    """
    Calls POST https://graph.microsoft.com/v1.0/copilot/retrieval
    with the delegated Graph token forwarded from the BFF.
    Maps the API response to CollaborationSignal items.
    """

    async def signals(self, query, context, *, graph_token, top=2):
        payload = {
            "queryString": f"{query} {context}",
            "maxResults": top,
        }
        headers = {"Authorization": f"Bearer {graph_token}"}
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://graph.microsoft.com/v1.0/copilot/retrieval",
                json=payload,
                headers=headers,
                timeout=5.0,
            )
        if resp.status_code != 200:
            return []  # graceful degradation
        items = resp.json().get("value", [])
        return [_map_retrieval_item(item) for item in items[:top]]
```

### 5.2 `FabricIQ` Protocol

```python
# apps/api/continuum/iq/fabric_iq.py

from typing import Protocol, runtime_checkable
from continuum.iq.types import BusinessMetric

@runtime_checkable
class FabricIQ(Protocol):
    async def metric(self, context: str) -> BusinessMetric | None:
        """
        Return one business metric relevant to `context`,
        or None if nothing applicable. Never raises.
        """
        ...
```

**`MockFabricIQ`** (default, no network):

```python
class MockFabricIQ:
    _METRIC: BusinessMetric = {
        "kind": "business_metric",
        "label": "Customer onboarding time",
        "value": "14 days avg (Q1 2025)",
        "direction": "down",
        "context": "Reduced 22 % after this process was standardised — now a key SLA target.",
        "source": "mock",
    }

    async def metric(self, context):
        return self._METRIC
```

**`FabricDataAgentClient`** (real, gated by config):

```python
class FabricDataAgentClient:
    """
    Queries a Fabric Data agent endpoint (HTTP POST) for a business metric.
    The agent is pre-configured in Fabric to answer metric questions against
    the organisation's lakehouse. Auth via API key or managed identity.
    """
    def __init__(self, endpoint: str, api_key: str):
        self._endpoint = endpoint
        self._api_key = api_key

    async def metric(self, context: str) -> BusinessMetric | None:
        payload = {"question": f"What is the key business metric for: {context}"}
        headers = {"x-api-key": self._api_key}
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self._endpoint, json=payload, headers=headers, timeout=8.0
            )
        if resp.status_code != 200:
            return None
        return _map_fabric_response(resp.json())
```

### 5.3 `IQClientFactory`

```python
# apps/api/continuum/iq/factory.py

from continuum.config import Settings

def make_work_iq(settings: Settings) -> WorkIQ:
    if settings.iq.work_iq_backend == "copilot":
        return CopilotRetrievalWorkIQ()
    return MockWorkIQ()

def make_fabric_iq(settings: Settings) -> FabricIQ:
    if settings.iq.fabric_iq_backend == "fabric":
        return FabricDataAgentClient(
            endpoint=settings.iq.fabric_agent_endpoint,
            api_key=settings.iq.fabric_agent_api_key,
        )
    return MockFabricIQ()
```

Both factories are called once at app startup (FastAPI lifespan) and injected as
FastAPI dependencies. The graph token is passed per-request, not at construction time.

### 5.4 Enrichment wiring into `MentorAgent`

Enrichment runs as a **post-retrieval step**, not as additional agent tools callable by
the model. Rationale: the model should stay grounded on Foundry IQ; enrichment is
additive context appended to the answer, not a reasoning branch the model controls.

**Updated `MentorAgent.stream` signature:**

```python
async def stream(
    self,
    successor: Successor,
    history: list[Message],
    user_message: str,
    *,
    graph_token: str,          # forwarded from BFF; "" when Work IQ is mocked
) -> AsyncIterator[ChatEvent]
```

**Turn sequence (extends Spec 2 §5):**

```
1. Foundry retrieve (existing — FoundryKnowledge.retrieve)
2. [NEW] WorkIQ.signals(query=user_message, context=retrieved_snippets_summary, graph_token=graph_token)
3. [NEW] FabricIQ.metric(context=retrieved_snippets_summary)
4. Model generates answer grounded on (1); enrichment from (2)+(3) appended to system prompt
   as additional context labelled "Collaboration context" / "Business context"
5. Citations event now carries FoundryCitation items + CollaborationSignal items + BusinessMetric item
6. Persist Message with extended citations JSONB
```

Enrichment calls (2) and (3) run **concurrently** (`asyncio.gather`), with a shared
timeout of 5 seconds. Either returning `[]`/`None` is silently ignored — the answer
still publishes with whatever Foundry IQ returned.

**New `ChatEvent` types** (additions to Spec 2's `ChatEvent`):

```python
@dataclass
class EnrichmentStarted:
    sources: list[str]   # e.g. ["work_iq", "fabric_iq"] — UI affordance "enriching…"

@dataclass
class Enrichment:
    signals: list[CollaborationSignal]
    metric: BusinessMetric | None
```

SSE protocol additions:

```
event: enrichment_started  data: {"sources": ["work_iq", "fabric_iq"]}
event: enrichment          data: {"signals": [...], "metric": {...} | null}
```

These events are emitted after `event: retrieval` and before the model starts streaming
text (so the UI can show the "enriching…" affordance during the concurrent fetch).

### 5.5 BFF — Graph token forwarding

The BFF chat proxy (Spec 2 §4.6) is extended to fetch and forward the Graph token:

```typescript
// apps/web/app/api/bff/conversations/[id]/messages/route.ts

import { auth } from "@/lib/auth"

export async function POST(req: Request, { params }) {
  const session = await auth.api.getSession({ headers: req.headers })
  if (!session) return new Response("Unauthorized", { status: 401 })

  // Existing: validate conversation org ownership
  // ...

  // NEW: fetch delegated Graph token for Work IQ
  const tokenResult = await auth.api.getAccessToken({
    providerId: "microsoft",
    userId: session.user.id,
  })
  const graphToken = tokenResult?.accessToken ?? ""

  // Forward to FastAPI with the token in a header
  const upstream = await fetch(`${FASTAPI_URL}/internal/conversations/${params.id}/messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Service-Token": process.env.SERVICE_TOKEN!,
      "X-User-Id": session.user.id,
      "X-Org-Id": session.session.activeOrganizationId!,
      "X-Graph-Token": graphToken,       // NEW — "" when no token
    },
    body: req.body,
    // @ts-expect-error duplex required for streaming POST
    duplex: "half",
  })

  return new Response(upstream.body, {
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
  })
}
```

FastAPI reads the token from `request.headers.get("x-graph-token", "")` and passes it
into `MentorAgent.stream(... graph_token=graph_token)`.

### 5.6 UI — enrichment rendering

The `assistant-ui` runtime adapter (Spec 2 §4.5) is extended to parse the two new SSE
events. The `Enrichment` event data is merged into the assistant message as structured
metadata and rendered as a distinct "Collaboration signals" + "Business context" section
below the main answer body and above the Foundry citations footer.

No new BFF routes are needed — enrichment flows through the same SSE stream.

## 6. Data Flow

```
Employee (browser)
  └─▶ POST /api/bff/conversations/{id}/messages
        BFF:
          1. validate Better Auth session + org ownership (existing)
          2. getAccessToken({providerId: "microsoft"}) → graphToken  [NEW]
          3. open SSE to FastAPI; headers: X-Service-Token, X-User-Id, X-Org-Id, X-Graph-Token

FastAPI POST /internal/conversations/{id}/messages  (SSE)
  1. load Successor (ready) + Conversation history
  2. query = user_message
  3. asyncio.gather(
       FoundryKnowledge.retrieve(kb, query, top=5),
       WorkIQ.signals(query, context="", graph_token=graph_token, top=2),  ← concurrent
       FabricIQ.metric(context=query),                                      ← concurrent
     ) with 5 s timeout
  4. emit: event: retrieval  data: {query}
  5. emit: event: enrichment_started  data: {sources}
  6. emit: event: enrichment  data: {signals, metric}   ← after gather completes
  7. MentorAgent runs model with:
       - Foundry snippets (grounding, as before)
       - Collaboration context appended to system prompt (signals)
       - Business context appended to system prompt (metric)
  8. emit: event: delta  data: {text}  (repeated)
  9. assemble citations = FoundryCitation[] + CollaborationSignal[] + BusinessMetric?
  10. emit: event: citations  data: [...]
  11. emit: event: done  data: {finish_reason}
  12. persist: user message; assistant message with extended citations JSONB

BFF relays SSE upstream (unchanged)
  └─▶ assistant-ui renders: streamed text + enrichment block + citations footer
```

Token audience path:
- Foundry IQ retrieve: managed identity (DefaultAzureCredential on Container Apps) — unchanged from Spec 2.
- Work IQ retrieve: `X-Graph-Token` (delegated, audience `https://graph.microsoft.com`) — provided by BFF.
- Fabric IQ metric: managed identity or API key on the Fabric Data agent endpoint — server-to-server.

## 7. Error Handling & Graceful Degradation

| Failure | Behaviour |
|---|---|
| Work IQ backend = "mock" (default) | `MockWorkIQ.signals` returns canned data; no Graph token needed. |
| Work IQ: no Copilot tenant / 403 from Graph | `CopilotRetrievalWorkIQ.signals` returns `[]`; enrichment event emitted with empty signals. |
| Work IQ: timeout (> 5 s) | `asyncio.gather` catches `asyncio.TimeoutError`; signals = `[]`. Answer proceeds on Foundry alone. |
| Work IQ: graph_token = "" (BFF couldn't fetch) | `CopilotRetrievalWorkIQ` returns `[]` without making the Graph call (token presence guard). |
| Fabric IQ backend = "mock" (default) | `MockFabricIQ.metric` returns canned metric. |
| Fabric IQ: no capacity / HTTP error | `FabricDataAgentClient.metric` returns `None`; enrichment event has `metric: null`. |
| Fabric IQ: timeout | `asyncio.TimeoutError` caught; metric = `None`. |
| Both enrichment providers fail | `event: enrichment` emitted as `{signals: [], metric: null}`; model answers grounded on Foundry only; this is a first-class acceptable outcome. |
| Foundry IQ unavailable | Existing Spec 2 error path (502 / `event: error`). Enrichment not relevant — the base answer fails. |

The system prompt instructs the model: if no collaboration signals or metric are present in
the context, do not mention them — do not fabricate enrichment from training data.

## 8. Testing Strategy

### Unit — `MentorAgent` enrichment path

Use `MockWorkIQ` + `MockFabricIQ` (the defaults) and the existing fake `FoundryKnowledge`
(Spec 2). Assert:

- `asyncio.gather` fires all three fetches concurrently (mock timing).
- `event: enrichment_started` is emitted before `event: delta`.
- `event: enrichment` carries the mock signals + metric.
- `event: citations` includes both `FoundryCitation` and `CollaborationSignal` items.
- When `WorkIQ.signals` returns `[]` and `FabricIQ.metric` returns `None`, the event is
  still emitted (empty) and the `done` event still fires — no partial failures.

### Unit — `CopilotRetrievalWorkIQ`

Mock the `httpx.AsyncClient`. Assert: correct `Authorization` header sent; HTTP 403 → `[]`;
HTTP 200 → correctly mapped `CollaborationSignal` list; empty `graph_token` → returns `[]`
without making the HTTP call.

### Unit — `FabricDataAgentClient`

Mock `httpx.AsyncClient`. Assert: correct payload shape; HTTP error → `None`; valid
response → correctly mapped `BusinessMetric`.

### Unit — `IQClientFactory`

Settings `work_iq_backend="mock"` → `MockWorkIQ`; `"copilot"` → `CopilotRetrievalWorkIQ`.
Same for Fabric IQ.

### API — SSE extended protocol

FastAPI `TestClient` with mock IQ backends. Assert event sequence:
`retrieval → enrichment_started → enrichment → delta* → citations → done`.
Assert that `Message.citations` JSONB contains all three kinds after persistence.

### Contract — Protocol compliance

Both `MockWorkIQ` and `CopilotRetrievalWorkIQ` pass the same parameterized test suite for
`WorkIQ`. Same for `FabricIQ`. Protects the swap point.

### Integration (gated `@integration`)

One test against real `CopilotRetrievalWorkIQ` requires a Copilot-licensed tenant +
a valid Graph token (injected from env). One test against `FabricDataAgentClient` requires
a live Fabric Data agent endpoint. Both are skipped without the relevant env vars.

### Web

Extend the existing assistant-ui runtime adapter test (Spec 2 §8) to parse the two new
SSE event types and assert that the enrichment block appears in the rendered message.

## 9. Acceptance Criteria

1. A mentor answer (Spec 2 demo flow) shows a "Collaboration signals" block with ≥1
   signal (e.g. "Maria led this…") alongside the Foundry citations, using mock data,
   with zero M365 or Fabric infrastructure required.
2. A mentor answer shows a "Business context" block with one metric (e.g. "Customer
   onboarding time: 14 days avg") using mock data.
3. Both blocks are persisted in `Message.citations` JSONB and survive a page reload.
4. Setting `work_iq_backend = "copilot"` with a valid Graph token activates
   `CopilotRetrievalWorkIQ` transparently — no other code changes.
5. Setting `fabric_iq_backend = "fabric"` with a valid endpoint activates
   `FabricDataAgentClient` transparently.
6. When both real backends fail (network error / timeout), the mentor answer still
   completes on Foundry IQ alone — the `done` event fires with no error.
7. The browser never sends the Graph token directly to FastAPI; it flows exclusively
   through the BFF.
8. All unit + contract tests pass without Azure/M365 credentials (`pytest -m "not integration"`).

## 10. Open Questions / Risks

| Item | Notes |
|---|---|
| **Copilot Retrieval API scope name** | Verify the exact delegated scope string on the target tenant (`Copilot.Chat.Read` or a tenant-specific value). Add to Better Auth `scope` in `auth.ts` before testing real Work IQ — a missing scope produces a silent 403. |
| **Graph token audience** | The Better Auth Microsoft provider issues tokens for `https://graph.microsoft.com`; confirm this is the correct audience for the Retrieval endpoint (it should be, as it's a Graph surface). If audience mismatch, token refresh with explicit `resource` param may be needed. |
| **Retrieval API response shape** | The `v1.0/copilot/retrieval` response schema should be validated against the live GA docs before writing `_map_retrieval_item`. Validate in an integration test or a one-off curl against a dev tenant early. |
| **Fabric Data agent HTTP interface** | The agent's invocation contract (URL, auth, request/response schema) must be confirmed with the Fabric setup. `FabricDataAgentClient` is a thin adapter — schema is internal and not standardised. |
| **Enrichment latency impact** | `asyncio.gather` runs enrichment concurrently with Foundry retrieve. If Work IQ or Fabric IQ are slow (> 3 s), the enrichment_started → enrichment gap is visible to the user. Hard timeout at 5 s is the guard; mock latency is 0 ms. |
| **Copilot content relevance** | The Copilot Retrieval API returns enterprise content scoped to the signed-in user's permissions. In a dev/sandbox tenant with minimal data, results may be empty or irrelevant — mock data is the demo safety net regardless. |
| **Token cost** | Work IQ calls consume Copilot capacity on the tenant; Fabric Data agent queries consume Fabric CU. Both are low-frequency (one call per mentor turn); no pooling needed for hackathon scale, but note for prod. |
| **Back-compat on `citations` JSONB** | Existing `Message` rows (Spec 2) have no `kind` field on citation items. Clients reading the extended schema must treat missing `kind` as `"foundry_citation"` — documented in §4.1. |
