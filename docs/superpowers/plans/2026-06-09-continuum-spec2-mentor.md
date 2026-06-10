# Spec 2 — Grounded Mentor Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new employee chats with the AI **Successor** for their role and gets streamed, grounded answers — every claim cited to the org's captured knowledge (Spec 1), with an honest "not in the org's knowledge" fallback instead of hallucination.

**Architecture:** We **own a bounded agent loop** (`MentorAgent`) over a `ChatModel` Protocol with exactly one tool — `retrieve` (= Spec 1's `FoundryKnowledge.retrieve`). A deterministic `FakeChatModel` is the default so the whole loop runs in CI with no Azure; the real `AzureOpenAIChatModel` (Azure OpenAI tool-calling, managed identity) sits behind the same Protocol and is verified by a gated `@integration` test. `Conversation`/`Message` persist in Postgres (Alembic 0003). A FastAPI **SSE** endpoint streams the turn; a Next.js BFF **streams the SSE through** to a minimal custom chat UI. Mirrors Spec 1's swappable-backend discipline exactly.

**Tech Stack:** FastAPI · SQLModel · Alembic · `openai` (AsyncAzureOpenAI) + `azure-identity` (real chat, gated) · Server-Sent Events (Python). Next.js BFF SSE proxy + a minimal streaming chat component (web). Defaults: `chat_backend=fake` (no Azure needed for dev/CI).

**Conventions:** Python cmds run from `apps/api`. Web cmds from repo root via `pnpm --filter web ...` + `pnpm check` (Biome). Append to every commit: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. NEVER `alembic revision --autogenerate` — hand-write migrations + add new tables to `_MANAGED_TABLES`. Reuse Spec 1's `require_service_token` + the `_org` header + the `successor_in_org` org guard.

---

## Architecture decisions (read before starting — these refine the design doc)

1. **We own the agent loop; the LLM call is the swap point.** `MentorAgent` runs a small bounded loop (≤4 iterations) over a `ChatModel` Protocol (`stream_turn(messages, tools) -> AsyncIterator[ChatModelEvent]`). This makes the loop deterministic + unit-testable against `FakeChatModel` with zero Azure. The real binding is **Azure OpenAI tool-calling** (`openai.AsyncAzureOpenAI`, GA, managed identity). This **supersedes the overview's "Microsoft Agent Framework" note for the single-tool mentor loop** — Agent Framework (multi-agent orchestration) buys us nothing for one tool + one loop and adds preview-API risk to the demo's emotional center. It can slot behind `ChatModel` later when multi-agent work appears. (Same swappable discipline as Spec 1's `FoundryKnowledge`.)
2. **Thread state lives in Postgres** (`Conversation`/`Message`), not Foundry managed threads — confirmed by the design (§3); gives Spec 3 the relational join.
3. **Web chat is a minimal custom SSE component**, not assistant-ui, as the concrete deliverable. It consumes the UI-agnostic SSE protocol (§6 of the design). assistant-ui can be layered later behind the same protocol (Task 13 notes the swap-in). Rationale: reliability for the demo > framework; the design itself names this as the fallback.
4. **Fake-first.** `chat_backend=fake` + Spec 1's `knowledge_backend=fake` ⇒ the entire chat loop (retrieve → grounded answer → citations) runs and is fully tested with no cloud creds.

## File structure

```
apps/api/src/continuum_api/
├── settings.py                       # + chat backend settings
├── models/
│   ├── conversation.py  message.py   # new tables
│   └── __init__.py                   # export both
├── agent/
│   ├── __init__.py
│   ├── types.py                      # ChatMessage, tool schema, ChatModelEvent*, MentorEvent*
│   ├── chat_model.py                 # ChatModel Protocol
│   ├── fake_chat.py                  # FakeChatModel (deterministic)
│   ├── azure_openai.py               # AzureOpenAIChatModel (real, gated)
│   ├── prompts.py                    # SystemPromptBuilder
│   ├── mentor.py                     # MentorAgent (the loop)
│   └── factory.py                    # settings-driven build_chat_model()
├── repos/conversation.py             # Conversation/Message repos
├── services/conversation.py          # ConversationService
├── routes/chat.py                    # FastAPI SSE chat endpoints
alembic/versions/0003_mentor.py       # conversation + message tables
apps/web/src/app/api/bff/conversations/[...path]/route.ts  # SSE-streaming proxy
apps/web/src/app/api/bff/successors/[id]/conversations/route.ts  # create-conversation proxy
apps/web/src/lib/chat-sse.ts          # SSE parser (browser)
apps/web/src/components/mentor-chat.tsx  # minimal streaming chat UI
apps/web/src/app/chat/[successorId]/page.tsx  # chat page
```

---

## Task 1: Chat dependencies + settings

**Files:** Modify `apps/api/pyproject.toml`, `apps/api/src/continuum_api/settings.py`

- [ ] **Step 1: Add deps** to `pyproject.toml` `[project.dependencies]` (keep existing): add `"openai>=1.54"`. (`azure-identity` is already a dep.) Then `uv sync` from `apps/api`. Expected: resolves, `uv.lock` updates.

- [ ] **Step 2: Extend `settings.py`** — add these fields to the `Settings` class (keep all existing fields; do not remove the `parents[4]` comment):
```python
    # Mentor chat backend — default fake so the loop runs without Azure OpenAI.
    chat_backend: Literal["fake", "azure_openai"] = "fake"

    # Azure OpenAI (only used when chat_backend == "azure_openai")
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = ""
    azure_openai_api_version: str = "2024-10-21"

    # Mentor tuning
    mentor_retrieve_top: int = 5
    mentor_max_iterations: int = 4
```

- [ ] **Step 3: Verify** (from `apps/api`): `uv run python -c "from continuum_api.settings import settings; print(settings.chat_backend, settings.mentor_max_iterations)"` → prints `fake 4`. Then `uv run ruff check .` → clean.

- [ ] **Step 4: Commit**
```bash
cd /home/skkippie/work/continuum
git add apps/api/pyproject.toml apps/api/uv.lock apps/api/src/continuum_api/settings.py
git commit -m "feat(mentor): add openai dep + chat backend settings (fake default)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Conversation + Message models

**Files:** Create `models/conversation.py`, `models/message.py`; modify `models/__init__.py`; create `tests/test_models_mentor.py`

- [ ] **Step 1: Write the failing test** `tests/test_models_mentor.py`:
```python
from continuum_api.models import Conversation, Message


def test_mentor_models_have_expected_tablenames():
    assert Conversation.__tablename__ == "conversation"
    assert Message.__tablename__ == "message"


def test_message_role_and_citations_default():
    m = Message(conversation_id="c1", role="user", content="hi")
    assert m.role == "user"
    assert m.citations is None
```

- [ ] **Step 2: Run, confirm fail** `cd /home/skkippie/work/continuum/apps/api && uv run pytest tests/test_models_mentor.py -v` → ImportError.

- [ ] **Step 3: Create `models/conversation.py`**:
```python
from datetime import datetime

from sqlmodel import Field, SQLModel


class Conversation(SQLModel, table=True):
    __tablename__ = "conversation"

    id: str = Field(primary_key=True)
    successor_id: str = Field(index=True)
    user_id: str = Field(index=True)  # Better Auth user id (no cross-ORM FK)
    title: str = Field(default="")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

- [ ] **Step 4: Create `models/message.py`** (citations is JSONB):
```python
from datetime import datetime
from typing import Any

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class Message(SQLModel, table=True):
    __tablename__ = "message"

    id: str = Field(primary_key=True)
    conversation_id: str = Field(index=True)
    role: str  # user | assistant
    content: str
    # [{title, source_document_id, snippet, score}] for assistant rows; null otherwise
    citations: list[dict[str, Any]] | None = Field(default=None, sa_column=Column(JSONB))
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

- [ ] **Step 5: Update `models/__init__.py`** — add the two imports + `__all__` entries (keep all existing capture/app_info exports), final `__all__` alphabetical:
```python
from continuum_api.models.app_info import AppInfo
from continuum_api.models.conversation import Conversation
from continuum_api.models.document import Document
from continuum_api.models.ingestion_job import IngestionJob
from continuum_api.models.knowledge_source import KnowledgeSource
from continuum_api.models.message import Message
from continuum_api.models.role import Role
from continuum_api.models.successor import Successor

__all__ = [
    "AppInfo",
    "Conversation",
    "Document",
    "IngestionJob",
    "KnowledgeSource",
    "Message",
    "Role",
    "Successor",
]
```

- [ ] **Step 6: Run, confirm pass** `cd /home/skkippie/work/continuum/apps/api && uv run pytest tests/test_models_mentor.py -v` → 2 passed. `uv run ruff check .` → clean. (`test_message_role_and_citations_default` is a pure in-memory check — no DB needed for it.)

- [ ] **Step 7: Commit**
```bash
cd /home/skkippie/work/continuum
git add apps/api/src/continuum_api/models apps/api/tests/test_models_mentor.py
git commit -m "feat(mentor): Conversation + Message models (citations JSONB)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Alembic 0003 — conversation + message tables

**Files:** Create `alembic/versions/0003_mentor.py`; modify `alembic/env.py` (`_MANAGED_TABLES`)

- [ ] **Step 1: Add the two tables to `_MANAGED_TABLES`** in `alembic/env.py` — the set must contain (add to whatever is there; do not remove):
```python
_MANAGED_TABLES = {
    "app_info",
    "role",
    "successor",
    "knowledge_source",
    "document",
    "ingestion_job",
    "conversation",
    "message",
}
```

- [ ] **Step 2: Hand-write `alembic/versions/0003_mentor.py`** (confirm `down_revision` matches the `revision` string in `0002_capture.py`, which is `"0002_capture"`):
```python
"""mentor: conversation, message"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003_mentor"
down_revision = "0002_capture"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("successor_id", sa.String, nullable=False, index=True),
        sa.Column("user_id", sa.String, nullable=False, index=True),
        sa.Column("title", sa.String, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "message",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("conversation_id", sa.String, nullable=False, index=True),
        sa.Column("role", sa.String, nullable=False),
        sa.Column("content", sa.String, nullable=False),
        sa.Column("citations", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("message")
    op.drop_table("conversation")
```

- [ ] **Step 3: Apply + verify coexistence** (Postgres up):
```bash
cd /home/skkippie/work/continuum/apps/api && uv run alembic upgrade head
cd /home/skkippie/work/continuum && docker compose exec -T postgres psql -U continuum -d continuum -c "\dt"
```
Expected: the 7 Better Auth tables + `app_info` + the 5 capture tables + `conversation` + `message` + `alembic_version`. **If any Better Auth table is gone → STOP, you ran autogenerate.**

- [ ] **Step 4: Tests green** `cd /home/skkippie/work/continuum/apps/api && uv run pytest -q` → all pass. `uv run ruff check .` → clean.

- [ ] **Step 5: Commit**
```bash
cd /home/skkippie/work/continuum
git add apps/api/alembic
git commit -m "feat(mentor): alembic 0003 creates conversation + message (Better Auth intact)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Agent types + ChatModel interface

**Files:** Create `agent/__init__.py`, `agent/types.py`, `agent/chat_model.py`

These are the stable contracts: the in-memory chat message shape, the `retrieve` tool schema, the low-level `ChatModelEvent`s the LLM emits, and the high-level `MentorEvent`s the agent streams to the API.

- [ ] **Step 1: Create `agent/types.py`**:
```python
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ChatMessage:
    """One message in the model's context window (NOT the persisted Message)."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None  # set on role="tool" rows
    tool_calls: list[dict[str, Any]] = field(default_factory=list)  # on assistant tool-call turns


# The single tool exposed to the model. `query` is the search string.
RETRIEVE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "retrieve",
        "description": (
            "Search the organization's captured knowledge for this role and return "
            "grounded snippets. Call this before answering any factual question."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for."}
            },
            "required": ["query"],
        },
    },
}


# --- low-level events the ChatModel streams ---------------------------------
@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ToolCallRequested:
    id: str
    name: str
    arguments_json: str  # raw JSON string of the tool arguments


@dataclass(frozen=True)
class TurnDone:
    finish_reason: str  # "tool_calls" | "stop" | ...


ChatModelEvent = TextDelta | ToolCallRequested | TurnDone


# --- high-level events MentorAgent streams to the API ----------------------
@dataclass(frozen=True)
class RetrievalStarted:
    query: str


@dataclass(frozen=True)
class Citation:
    title: str
    source_document_id: str
    snippet: str
    score: float


@dataclass(frozen=True)
class Citations:
    items: list[Citation]


@dataclass(frozen=True)
class MentorDone:
    finish_reason: str


# TextDelta is reused for assistant text; MentorEvent is the union the API relays.
MentorEvent = TextDelta | RetrievalStarted | Citations | MentorDone
```

- [ ] **Step 2: Create `agent/chat_model.py`** (the swap point):
```python
from collections.abc import AsyncIterator
from typing import Any, Protocol

from continuum_api.agent.types import ChatMessage, ChatModelEvent


class ChatModel(Protocol):
    def stream_turn(
        self, messages: list[ChatMessage], tools: list[dict[str, Any]]
    ) -> AsyncIterator[ChatModelEvent]: ...
```

- [ ] **Step 3: Create `agent/__init__.py`**:
```python
# agent package
```

- [ ] **Step 4: Verify import** `cd /home/skkippie/work/continuum/apps/api && uv run python -c "from continuum_api.agent.chat_model import ChatModel; from continuum_api.agent.types import RETRIEVE_TOOL, MentorDone; print('ok')"` → `ok`. `uv run ruff check .` → clean.

- [ ] **Step 5: Commit**
```bash
cd /home/skkippie/work/continuum
git add apps/api/src/continuum_api/agent
git commit -m "feat(mentor): agent types + ChatModel protocol (the swap point)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: FakeChatModel (deterministic) — TDD

**Files:** Create `agent/fake_chat.py`, `tests/test_fake_chat.py`

The fake emulates a tool-using model deterministically: if the message list contains **no `tool` message yet**, it requests `retrieve(query=<last user message>)`; once a `tool` result is present, it emits a templated answer built from that tool content (or the honest "I don't know" line when the tool content is empty).

- [ ] **Step 1: Write failing test** `tests/test_fake_chat.py`:
```python
import pytest

from continuum_api.agent.fake_chat import FakeChatModel
from continuum_api.agent.types import (
    ChatMessage, RETRIEVE_TOOL, TextDelta, ToolCallRequested, TurnDone,
)


async def _collect(aiter):
    return [e async for e in aiter]


@pytest.mark.asyncio
async def test_first_turn_requests_retrieve():
    model = FakeChatModel()
    msgs = [ChatMessage(role="system", content="..."),
            ChatMessage(role="user", content="why do we deploy on fridays?")]
    events = await _collect(model.stream_turn(msgs, [RETRIEVE_TOOL]))
    assert any(isinstance(e, ToolCallRequested) and e.name == "retrieve" for e in events)
    assert isinstance(events[-1], TurnDone) and events[-1].finish_reason == "tool_calls"


@pytest.mark.asyncio
async def test_second_turn_answers_from_tool_content():
    model = FakeChatModel()
    msgs = [
        ChatMessage(role="user", content="why fridays?"),
        ChatMessage(role="assistant", content="",
                    tool_calls=[{"id": "t1", "name": "retrieve"}]),
        ChatMessage(role="tool", tool_call_id="t1",
                    content="We deploy on Fridays to avoid mid-week risk."),
    ]
    events = await _collect(model.stream_turn(msgs, [RETRIEVE_TOOL]))
    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert "Fridays" in text
    assert isinstance(events[-1], TurnDone) and events[-1].finish_reason == "stop"


@pytest.mark.asyncio
async def test_empty_tool_content_says_i_dont_know():
    model = FakeChatModel()
    msgs = [
        ChatMessage(role="user", content="what is the wifi password?"),
        ChatMessage(role="assistant", content="",
                    tool_calls=[{"id": "t1", "name": "retrieve"}]),
        ChatMessage(role="tool", tool_call_id="t1", content=""),
    ]
    events = await _collect(model.stream_turn(msgs, [RETRIEVE_TOOL]))
    text = "".join(e.text for e in events if isinstance(e, TextDelta)).lower()
    assert "don't have" in text or "do not have" in text
```

- [ ] **Step 2: Run, confirm fail** `cd /home/skkippie/work/continuum/apps/api && uv run pytest tests/test_fake_chat.py -v` → ImportError. (Note: `pytest-asyncio` must be available — see Step 3.)

- [ ] **Step 3: Ensure async test support.** Check `apps/api/pyproject.toml` for `pytest-asyncio`. If absent, add it to the dev deps and configure auto mode: in `pyproject.toml` add under `[tool.pytest.ini_options]` (create the table if missing) `asyncio_mode = "auto"`, and add `pytest-asyncio>=0.24` to the dev dependency group used by `uv` (mirror however existing dev deps like `pytest` are declared — read the file first). Run `uv sync`. With `asyncio_mode = "auto"`, the `@pytest.mark.asyncio` decorators are optional but harmless; keep them for clarity.

- [ ] **Step 4: Create `agent/fake_chat.py`**:
```python
from collections.abc import AsyncIterator

from continuum_api.agent.types import (
    ChatMessage, ChatModelEvent, TextDelta, ToolCallRequested, TurnDone,
)


class FakeChatModel:
    """Deterministic ChatModel: retrieve first, then a templated grounded answer."""

    async def stream_turn(
        self, messages: list[ChatMessage], tools: list
    ) -> AsyncIterator[ChatModelEvent]:
        tool_msgs = [m for m in messages if m.role == "tool"]
        if not tool_msgs:
            last_user = next(
                (m.content for m in reversed(messages) if m.role == "user"), ""
            )
            yield ToolCallRequested(
                id="fake-call-1", name="retrieve",
                arguments_json=f'{{"query": {last_user!r}}}'.replace("'", '"'),
            )
            yield TurnDone(finish_reason="tool_calls")
            return

        tool_content = tool_msgs[-1].content.strip()
        if not tool_content:
            for chunk in ("I don't have that ", "in the org's knowledge yet."):
                yield TextDelta(text=chunk)
            yield TurnDone(finish_reason="stop")
            return

        # Templated grounded answer: a short framing + the retrieved content.
        answer = f"Based on the team's knowledge: {tool_content}"
        for word in answer.split(" "):
            yield TextDelta(text=word + " ")
        yield TurnDone(finish_reason="stop")
```

- [ ] **Step 5: Run, confirm pass** `cd /home/skkippie/work/continuum/apps/api && uv run pytest tests/test_fake_chat.py -v` → 3 passed. `uv run ruff check .` → clean.

- [ ] **Step 6: Commit**
```bash
cd /home/skkippie/work/continuum
git add apps/api/pyproject.toml apps/api/uv.lock apps/api/src/continuum_api/agent/fake_chat.py apps/api/tests/test_fake_chat.py
git commit -m "feat(mentor): FakeChatModel (deterministic retrieve-then-answer) + async test setup

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: SystemPromptBuilder — TDD

**Files:** Create `agent/prompts.py`, `tests/test_prompts.py`

- [ ] **Step 1: Write failing test** `tests/test_prompts.py`:
```python
from continuum_api.agent.prompts import build_system_prompt
from continuum_api.models import Role, Successor


def test_system_prompt_frames_the_role_and_grounding_rules():
    role = Role(id="r1", org_id="o1", title="Support Lead", description="Owns refunds")
    successor = Successor(id="s1", role_id="r1", knowledge_base_name="kb")
    prompt = build_system_prompt(role, successor)
    assert "Support Lead" in prompt
    # grounding contract is spelled out
    low = prompt.lower()
    assert "retrieve" in low
    assert "cite" in low or "citation" in low
    assert "don't" in low or "do not" in low  # the honest-fallback instruction
```

- [ ] **Step 2: Run, confirm fail** `cd /home/skkippie/work/continuum/apps/api && uv run pytest tests/test_prompts.py -v` → ImportError.

- [ ] **Step 3: Create `agent/prompts.py`**:
```python
from continuum_api.models import Role, Successor


def build_system_prompt(role: Role, successor: Successor) -> str:
    summary = successor.summary or role.description or "this role"
    return (
        f"You are the AI successor for the role **{role.title}** at this organization. "
        f"Your job is to mentor a new employee: teach them not just WHAT the team does "
        f"but WHY. Context for the role: {summary}\n\n"
        "Rules:\n"
        "1. Before answering any factual question, call the `retrieve` tool to search the "
        "organization's captured knowledge.\n"
        "2. Answer ONLY from the retrieved snippets. Do not invent facts.\n"
        "3. Cite the sources you used. Every claim should trace to a retrieved snippet.\n"
        "4. If retrieval returns nothing relevant, say plainly that you don't have that "
        "in the org's knowledge yet — never guess.\n"
        "5. Be concise, concrete, and warm — you are onboarding a colleague."
    )
```

- [ ] **Step 4: Run, confirm pass** `cd /home/skkippie/work/continuum/apps/api && uv run pytest tests/test_prompts.py -v` → 1 passed. `uv run ruff check .` → clean.

- [ ] **Step 5: Commit**
```bash
cd /home/skkippie/work/continuum
git add apps/api/src/continuum_api/agent/prompts.py apps/api/tests/test_prompts.py
git commit -m "feat(mentor): SystemPromptBuilder (successor framing + grounding contract)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: MentorAgent (the loop) — TDD vs fakes

**Files:** Create `agent/mentor.py`, `tests/test_mentor_agent.py`

`MentorAgent.stream` builds the model context (system + mapped history + new user message), runs the bounded loop over the injected `ChatModel`: relay `TextDelta`s, and on a `retrieve` `ToolCallRequested` emit `RetrievalStarted`, call `FoundryKnowledge.retrieve`, append the assistant tool-call + tool-result messages, and continue. After the model stops, emit `Citations` (assembled from the snippets actually retrieved) then `MentorDone`.

- [ ] **Step 1: Write failing test** `tests/test_mentor_agent.py`:
```python
import pytest

from continuum_api.agent.fake_chat import FakeChatModel
from continuum_api.agent.mentor import MentorAgent
from continuum_api.agent.types import Citations, MentorDone, RetrievalStarted, TextDelta
from continuum_api.knowledge.fake import FakeFoundryKnowledge
from continuum_api.knowledge.local_blob import LocalBlobStore
from continuum_api.models import Role, Successor


def _knowledge(tmp_path, text: str):
    blob = LocalBlobStore(root=str(tmp_path))
    container = blob.ensure_container("s1")
    blob.put(container, "doc.txt", text.encode("utf-8"), "text/plain")
    kn = FakeFoundryKnowledge(blob)
    kn.ensure_knowledge_base("kb")
    kn.ensure_blob_source("kb", container)
    kn.start_indexing("kb")
    return kn


def _agent(kn):
    role = Role(id="r1", org_id="o1", title="Support Lead")
    successor = Successor(id="s1", role_id="r1", knowledge_base_name="kb")
    return MentorAgent(FakeChatModel(), kn, role, successor)


async def _collect(aiter):
    return [e async for e in aiter]


@pytest.mark.asyncio
async def test_grounded_answer_has_citations_in_order(tmp_path):
    kn = _knowledge(tmp_path, "We deploy on Fridays to avoid mid-week risk.")
    events = await _collect(_agent(kn).stream([], "why do we deploy on fridays?"))
    kinds = [type(e).__name__ for e in events]
    # retrieval announced, text streamed, citations, then done — in that order
    assert "RetrievalStarted" in kinds
    assert kinds.index("Citations") < kinds.index("MentorDone")
    assert all(kinds.index(d) < kinds.index("Citations")
               for d in kinds if d == "TextDelta")
    cites = next(e for e in events if isinstance(e, Citations))
    assert cites.items and cites.items[0].source_document_id == "doc.txt"
    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert "Fridays" in text


@pytest.mark.asyncio
async def test_unanswerable_question_no_citations_and_honest(tmp_path):
    kn = _knowledge(tmp_path, "We deploy on Fridays.")
    events = await _collect(
        _agent(kn).stream([], "what is the office wifi password?")
    )
    cites = next(e for e in events if isinstance(e, Citations))
    assert cites.items == []  # no fabricated citations
    text = "".join(e.text for e in events if isinstance(e, TextDelta)).lower()
    assert "don't have" in text or "do not have" in text
    assert isinstance(events[-1], MentorDone)
```

- [ ] **Step 2: Run, confirm fail** `cd /home/skkippie/work/continuum/apps/api && uv run pytest tests/test_mentor_agent.py -v` → ImportError.

- [ ] **Step 3: Create `agent/mentor.py`**:
```python
import json
from collections.abc import AsyncIterator

from continuum_api.agent.chat_model import ChatModel
from continuum_api.agent.prompts import build_system_prompt
from continuum_api.agent.types import (
    RETRIEVE_TOOL,
    ChatMessage,
    Citation,
    Citations,
    MentorDone,
    MentorEvent,
    RetrievalStarted,
    TextDelta,
    ToolCallRequested,
    TurnDone,
)
from continuum_api.knowledge.interface import FoundryKnowledge
from continuum_api.knowledge.types import RetrievedSnippet
from continuum_api.models import Message, Role, Successor


class MentorAgent:
    def __init__(
        self,
        chat_model: ChatModel,
        knowledge: FoundryKnowledge,
        role: Role,
        successor: Successor,
        *,
        retrieve_top: int = 5,
        max_iterations: int = 4,
    ) -> None:
        self._chat = chat_model
        self._kn = knowledge
        self._role = role
        self._successor = successor
        self._top = retrieve_top
        self._max_iter = max_iterations

    def _history_to_messages(self, history: list[Message]) -> list[ChatMessage]:
        out: list[ChatMessage] = []
        for m in history:
            if m.role in ("user", "assistant"):
                out.append(ChatMessage(role=m.role, content=m.content))
        return out

    async def stream(
        self, history: list[Message], user_message: str
    ) -> AsyncIterator[MentorEvent]:
        messages: list[ChatMessage] = [
            ChatMessage(role="system",
                        content=build_system_prompt(self._role, self._successor)),
            *self._history_to_messages(history),
            ChatMessage(role="user", content=user_message),
        ]
        used: list[RetrievedSnippet] = []
        finish = "stop"

        for _ in range(self._max_iter):
            tool_calls_this_turn: list[tuple[str, str]] = []  # (id, query)
            assistant_text = ""
            turn_finish = "stop"
            async for ev in self._chat.stream_turn(messages, [RETRIEVE_TOOL]):
                if isinstance(ev, TextDelta):
                    assistant_text += ev.text
                    yield ev
                elif isinstance(ev, ToolCallRequested) and ev.name == "retrieve":
                    query = _parse_query(ev.arguments_json)
                    tool_calls_this_turn.append((ev.id, query))
                elif isinstance(ev, TurnDone):
                    turn_finish = ev.finish_reason

            if not tool_calls_this_turn:
                finish = turn_finish
                break

            # Record the assistant tool-call turn, then run each retrieve + feed results.
            messages.append(ChatMessage(
                role="assistant", content=assistant_text,
                tool_calls=[{"id": cid, "name": "retrieve"} for cid, _ in tool_calls_this_turn],
            ))
            for cid, query in tool_calls_this_turn:
                yield RetrievalStarted(query=query)
                snippets = self._kn.retrieve(
                    self._successor.knowledge_base_name, query, top=self._top
                )
                used.extend(snippets)
                messages.append(ChatMessage(
                    role="tool", tool_call_id=cid,
                    content="\n\n".join(s.content for s in snippets),
                ))
        else:
            finish = "max_iterations"

        yield Citations(items=[
            Citation(title=s.title, source_document_id=s.source_document_id,
                     snippet=s.content, score=s.score)
            for s in _dedupe(used)
        ])
        yield MentorDone(finish_reason=finish)


def _parse_query(arguments_json: str) -> str:
    try:
        return str(json.loads(arguments_json).get("query", "")).strip()
    except (ValueError, TypeError):
        return ""


def _dedupe(snippets: list[RetrievedSnippet]) -> list[RetrievedSnippet]:
    seen: set[tuple[str, str]] = set()
    out: list[RetrievedSnippet] = []
    for s in snippets:
        key = (s.source_document_id, s.content)
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out
```
NOTE: Citations are assembled from the snippets the agent retrieved (design §4.1: "cite all retrieved snippets the turn used; refine to 'actually referenced' later"), so an empty-retrieval turn yields `Citations(items=[])` and the fake's honest "I don't have that" text — exactly the unanswerable-question contract.

- [ ] **Step 4: Run, confirm pass** `cd /home/skkippie/work/continuum/apps/api && uv run pytest tests/test_mentor_agent.py -v` → 2 passed. `uv run ruff check .` → clean.

- [ ] **Step 5: Commit**
```bash
cd /home/skkippie/work/continuum
git add apps/api/src/continuum_api/agent/mentor.py apps/api/tests/test_mentor_agent.py
git commit -m "feat(mentor): MentorAgent bounded loop (retrieve tool, citations, honest fallback)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: ConversationService + repos — TDD

**Files:** Create `repos/conversation.py`, `services/conversation.py`, `tests/test_conversation_service.py`

- [ ] **Step 1: Write failing test** `tests/test_conversation_service.py`:
```python
import uuid

from sqlmodel import Session

from continuum_api.db import engine
from continuum_api.services.conversation import ConversationService


def _svc():
    session = Session(engine)
    return ConversationService(session), session


def test_create_append_history_and_title():
    svc, session = _svc()
    sid = f"s-{uuid.uuid4().hex[:8]}"
    uid = f"u-{uuid.uuid4().hex[:8]}"
    convo = svc.create(successor_id=sid, user_id=uid)
    svc.append(convo.id, role="user", content="Why do we deploy on Fridays exactly?")
    svc.append(convo.id, role="assistant", content="Because…",
               citations=[{"title": "doc.txt", "source_document_id": "doc.txt",
                           "snippet": "…", "score": 1.0}])
    session.commit()

    msgs = svc.history(convo.id)
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[1].citations and msgs[1].citations[0]["source_document_id"] == "doc.txt"
    # title derived from the first user message (truncated)
    refreshed = svc.get(convo.id)
    assert refreshed.title.startswith("Why do we deploy")
```

- [ ] **Step 2: Run, confirm fail** `cd /home/skkippie/work/continuum/apps/api && uv run pytest tests/test_conversation_service.py -v` → ImportError.

- [ ] **Step 3: Create `repos/conversation.py`**:
```python
from sqlmodel import Session, select

from continuum_api.models import Conversation, Message


class ConversationRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, convo: Conversation) -> Conversation:
        self._s.add(convo)
        return convo

    def get(self, conversation_id: str) -> Conversation | None:
        return self._s.get(Conversation, conversation_id)


class MessageRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, message: Message) -> Message:
        self._s.add(message)
        return message

    def for_conversation(self, conversation_id: str) -> list[Message]:
        return list(self._s.exec(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        ))
```

- [ ] **Step 4: Create `services/conversation.py`**:
```python
import uuid
from datetime import datetime
from typing import Any

from sqlmodel import Session

from continuum_api.models import Conversation, Message
from continuum_api.repos.conversation import ConversationRepo, MessageRepo

_TITLE_MAX = 60


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


class ConversationService:
    def __init__(self, session: Session) -> None:
        self._s = session
        self.conversations = ConversationRepo(session)
        self.messages = MessageRepo(session)

    def create(self, *, successor_id: str, user_id: str) -> Conversation:
        convo = self.conversations.create(
            Conversation(id=_id("conv"), successor_id=successor_id, user_id=user_id)
        )
        self._s.flush()
        return convo

    def get(self, conversation_id: str) -> Conversation | None:
        return self.conversations.get(conversation_id)

    def history(self, conversation_id: str) -> list[Message]:
        return self.messages.for_conversation(conversation_id)

    def append(
        self, conversation_id: str, *, role: str, content: str,
        citations: list[dict[str, Any]] | None = None,
    ) -> Message:
        msg = self.messages.create(Message(
            id=_id("msg"), conversation_id=conversation_id, role=role,
            content=content, citations=citations,
        ))
        convo = self.conversations.get(conversation_id)
        if convo is not None:
            convo.updated_at = datetime.utcnow()
            if not convo.title and role == "user":
                convo.title = content[:_TITLE_MAX]
        self._s.flush()
        return msg
```

- [ ] **Step 5: Run, confirm pass** `cd /home/skkippie/work/continuum/apps/api && uv run pytest tests/test_conversation_service.py -v` → 1 passed. Full suite `uv run pytest -q` → all pass. `uv run ruff check .` → clean.

- [ ] **Step 6: Commit**
```bash
cd /home/skkippie/work/continuum
git add apps/api/src/continuum_api/repos/conversation.py apps/api/src/continuum_api/services/conversation.py apps/api/tests/test_conversation_service.py
git commit -m "feat(mentor): ConversationService (create/append/history, title from first msg)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Chat model factory (settings-driven)

**Files:** Create `agent/factory.py`, `tests/test_chat_factory.py`

- [ ] **Step 1: Write failing test** `tests/test_chat_factory.py`:
```python
from continuum_api.agent.factory import build_chat_model
from continuum_api.agent.fake_chat import FakeChatModel


def test_default_chat_model_is_fake():
    assert isinstance(build_chat_model(), FakeChatModel)
```

- [ ] **Step 2: Run, confirm fail** → ImportError.

- [ ] **Step 3: Create `agent/factory.py`** (lazy Azure import; stateless so no singleton):
```python
from continuum_api.agent.chat_model import ChatModel
from continuum_api.settings import settings


def build_chat_model() -> ChatModel:
    if settings.chat_backend == "azure_openai":
        from continuum_api.agent.azure_openai import AzureOpenAIChatModel

        return AzureOpenAIChatModel(
            endpoint=settings.azure_openai_endpoint,
            deployment=settings.azure_openai_deployment,
            api_version=settings.azure_openai_api_version,
        )
    from continuum_api.agent.fake_chat import FakeChatModel

    return FakeChatModel()
```

- [ ] **Step 4: Run, confirm pass** → 1 passed. `uv run ruff check .` → clean.

- [ ] **Step 5: Commit**
```bash
cd /home/skkippie/work/continuum
git add apps/api/src/continuum_api/agent/factory.py apps/api/tests/test_chat_factory.py
git commit -m "feat(mentor): settings-driven chat model factory (lazy Azure import)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Chat API (FastAPI, SSE) — TDD with TestClient

**Files:** Create `routes/chat.py`, `tests/test_chat_api.py`; modify `main.py`

Reuses Spec 1's `require_service_token`, the `_org` header dependency, and the `successor_in_org` org guard (via an `IngestionService` built from Spec 1's factory). Three endpoints; the message endpoint streams SSE.

- [ ] **Step 1: Write failing test** `tests/test_chat_api.py` (drives the full Spec 1 capture loop first so the Successor is `ready`, then chats):
```python
import json
import uuid


def _h():
    from continuum_api.settings import settings
    return {"X-Service-Token": settings.api_service_token, "X-Org-Id": "o-chat"}


def _ready_successor(client, h):
    role_id = f"r-{uuid.uuid4().hex[:8]}"
    client.post("/internal/roles", json={"id": role_id, "title": "Ops"}, headers=h)
    sid = client.post(f"/internal/roles/{role_id}/successor", headers=h).json()["id"]
    client.post(f"/internal/successors/{sid}/documents",
                files=[("files", ("p.txt", b"We deploy on Fridays to reduce risk.",
                                   "text/plain"))], headers=h)
    client.post(f"/internal/successors/{sid}/ingest", headers=h)
    assert client.get(f"/internal/successors/{sid}", headers=h).json()["status"] == "ready"
    return sid


def _parse_sse(raw: str) -> list[tuple[str, str]]:
    events = []
    for block in raw.strip().split("\n\n"):
        ev, data = None, None
        for line in block.splitlines():
            if line.startswith("event:"):
                ev = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data = line[len("data:"):].strip()
        if ev:
            events.append((ev, data or ""))
    return events


def test_chat_streams_grounded_answer_with_citations(client):
    h = _h()
    sid = _ready_successor(client, h)
    convo = client.post(f"/internal/successors/{sid}/conversations", headers=h)
    assert convo.status_code == 201
    cid = convo.json()["id"]

    r = client.post(f"/internal/conversations/{cid}/messages",
                    json={"content": "why do we deploy on fridays?"}, headers=h)
    assert r.status_code == 200
    events = _parse_sse(r.text)
    kinds = [e for e, _ in events]
    assert "delta" in kinds
    assert "citations" in kinds
    assert kinds[-1] == "done"
    # citations carry a real source document id
    cite_data = next(d for e, d in events if e == "citations")
    cites = json.loads(cite_data)
    assert cites and cites[0]["source_document_id"] == "p.txt"

    # persisted: user + assistant message reload
    history = client.get(f"/internal/conversations/{cid}", headers=h).json()
    assert [m["role"] for m in history["messages"]] == ["user", "assistant"]
    assert history["messages"][1]["citations"]


def test_conversation_create_requires_ready_successor(client):
    h = _h()
    role_id = f"r-{uuid.uuid4().hex[:8]}"
    client.post("/internal/roles", json={"id": role_id, "title": "X"}, headers=h)
    sid = client.post(f"/internal/roles/{role_id}/successor", headers=h).json()["id"]
    # no docs ingested → still provisioning → 409
    r = client.post(f"/internal/successors/{sid}/conversations", headers=h)
    assert r.status_code == 409


def test_cross_org_conversation_is_404(client):
    a = _h()
    b = {"X-Service-Token": a["X-Service-Token"], "X-Org-Id": "other-org"}
    sid = _ready_successor(client, a)
    cid = client.post(f"/internal/successors/{sid}/conversations", headers=a).json()["id"]
    assert client.get(f"/internal/conversations/{cid}", headers=b).status_code == 404
    assert client.post(f"/internal/conversations/{cid}/messages",
                       json={"content": "hi"}, headers=b).status_code == 404
```

- [ ] **Step 2: Run, confirm fail** `cd /home/skkippie/work/continuum/apps/api && uv run pytest tests/test_chat_api.py -v` → 404 (routes absent).

- [ ] **Step 3: Create `routes/chat.py`**:
```python
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session

from continuum_api.agent.factory import build_chat_model
from continuum_api.agent.mentor import MentorAgent
from continuum_api.agent.types import (
    Citations, MentorDone, RetrievalStarted, TextDelta,
)
from continuum_api.db import get_session
from continuum_api.knowledge.factory import build_blob_store, build_knowledge
from continuum_api.routes.capture import _org  # reuse the X-Org-Id dependency
from continuum_api.routes.internal import require_service_token
from continuum_api.services.conversation import ConversationService
from continuum_api.services.ingestion import IngestionService
from continuum_api.settings import settings

router = APIRouter(prefix="/internal", dependencies=[Depends(require_service_token)])


def _capture(session: Session) -> IngestionService:
    blob = build_blob_store()
    return IngestionService(session, blob, build_knowledge(blob))


class CreateConversation(BaseModel):
    pass


class SendMessage(BaseModel):
    content: str


def _sse(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


@router.post("/successors/{successor_id}/conversations", status_code=201)
def create_conversation(successor_id: str, org: str = Depends(_org),
                        session: Session = Depends(get_session)) -> dict:
    capture = _capture(session)
    if not capture.successor_in_org(successor_id, org):
        raise HTTPException(status_code=404, detail="not found")
    successor = capture.get_successor(successor_id)
    if successor is None:
        raise HTTPException(status_code=404, detail="not found")
    if successor.status != "ready":
        raise HTTPException(status_code=409, detail="successor still learning this role")
    convo = ConversationService(session).create(successor_id=successor_id, user_id=org)
    session.commit()
    return {"id": convo.id}


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, org: str = Depends(_org),
                     session: Session = Depends(get_session)) -> dict:
    convo = ConversationService(session).get(conversation_id)
    if convo is None or not _capture(session).successor_in_org(convo.successor_id, org):
        raise HTTPException(status_code=404, detail="not found")
    msgs = ConversationService(session).history(conversation_id)
    return {"id": convo.id, "title": convo.title, "messages": [
        {"role": m.role, "content": m.content, "citations": m.citations} for m in msgs
    ]}


@router.post("/conversations/{conversation_id}/messages")
async def send_message(conversation_id: str, body: SendMessage, org: str = Depends(_org),
                       session: Session = Depends(get_session)) -> StreamingResponse:
    convos = ConversationService(session)
    convo = convos.get(conversation_id)
    capture = _capture(session)
    if convo is None or not capture.successor_in_org(convo.successor_id, org):
        raise HTTPException(status_code=404, detail="not found")
    successor = capture.get_successor(convo.successor_id)
    role = capture.roles.get(successor.role_id)
    if successor.status != "ready":
        raise HTTPException(status_code=409, detail="successor still learning this role")

    history = convos.history(conversation_id)
    agent = MentorAgent(
        build_chat_model(), build_knowledge(build_blob_store()), role, successor,
        retrieve_top=settings.mentor_retrieve_top,
        max_iterations=settings.mentor_max_iterations,
    )

    async def gen() -> AsyncIterator[str]:
        answer = ""
        citations: list[dict] = []
        finish = "stop"
        try:
            async for ev in agent.stream(history, body.content):
                if isinstance(ev, TextDelta):
                    answer += ev.text
                    yield _sse("delta", json.dumps({"text": ev.text}))
                elif isinstance(ev, RetrievalStarted):
                    yield _sse("retrieval", json.dumps({"query": ev.query}))
                elif isinstance(ev, Citations):
                    citations = [
                        {"title": c.title, "source_document_id": c.source_document_id,
                         "snippet": c.snippet, "score": c.score} for c in ev.items
                    ]
                    yield _sse("citations", json.dumps(citations))
                elif isinstance(ev, MentorDone):
                    finish = ev.finish_reason
            # persist only after a clean finish
            convos.append(conversation_id, role="user", content=body.content)
            convos.append(conversation_id, role="assistant", content=answer,
                          citations=citations or None)
            session.commit()
            yield _sse("done", json.dumps({"finish_reason": finish}))
        except Exception as exc:  # noqa: BLE001 — surface a typed SSE error, then close
            session.rollback()
            yield _sse("error", json.dumps({"detail": str(exc)}))

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```
NOTE: `user_id` is set to `org` as a stand-in (the BFF forwards the org; a real per-user id arrives once the BFF forwards `X-User-Id` — Spec 1 left that wired-but-unused). `successor.status != "ready"` returns 409 per design §7. `X-Accel-Buffering: no` + `Cache-Control: no-cache` keep proxies from buffering the stream.

- [ ] **Step 4: Register the router in `main.py`** — add `from continuum_api.routes import chat` (extend the existing import line: `from continuum_api.routes import capture, chat, health, internal`) and `app.include_router(chat.router)` after `capture`. Keep `serve()`.

- [ ] **Step 5: Run, confirm pass** `cd /home/skkippie/work/continuum/apps/api && uv run pytest tests/test_chat_api.py -v` → 3 passed. Full suite `uv run pytest -q` → all pass. `uv run ruff check .` → clean.
  - If the SSE test sees no `citations`: confirm the fake knowledge singleton indexed the doc (Spec 1 capture ran in the same test via the API → same process singleton) and that `mentor_retrieve_top` > 0. If `delta` text lacks "Fridays", confirm the fake's prefix-match handled "fridays"/"Fridays" (it lowercases).

- [ ] **Step 6: Commit**
```bash
cd /home/skkippie/work/continuum
git add apps/api/src/continuum_api/routes/chat.py apps/api/src/continuum_api/main.py apps/api/tests/test_chat_api.py
git commit -m "feat(mentor): FastAPI SSE chat endpoints (conversations + streamed messages)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: AzureOpenAIChatModel (real) — gated integration

**Files:** Create `agent/azure_openai.py`, `tests/test_azure_openai_integration.py`

Implements `ChatModel` over `openai.AsyncAzureOpenAI` with managed-identity token provider + streaming tool calls. Verified only when `RUN_AZURE_INTEGRATION=1` + Azure OpenAI creds are present; otherwise the test SKIPS (CI stays green). **Pre-step (recommended):** confirm the installed `openai` version's streaming tool-call delta shape (`chunk.choices[0].delta.tool_calls[*].function.{name,arguments}`) — it is GA + stable, but verify before the IT.

- [ ] **Step 1: Create `agent/azure_openai.py`** (keep `openai`/`azure.identity` imports lazy so the module imports without the SDKs configured — only stdlib + our types at top level):
```python
from collections.abc import AsyncIterator
from typing import Any

from continuum_api.agent.types import (
    ChatMessage, ChatModelEvent, TextDelta, ToolCallRequested, TurnDone,
)


def _to_openai(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "tool":
            out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
        elif m.role == "assistant" and m.tool_calls:
            out.append({
                "role": "assistant", "content": m.content or None,
                "tool_calls": [
                    {"id": tc["id"], "type": "function",
                     "function": {"name": tc["name"], "arguments": "{}"}}
                    for tc in m.tool_calls
                ],
            })
        else:
            out.append({"role": m.role, "content": m.content})
    return out


class AzureOpenAIChatModel:
    """Real ChatModel over Azure OpenAI tool-calling (managed identity).

    NOTE: streaming tool-call delta shape targets the GA openai SDK; the
    auth/token-provider wiring is verified by the gated integration test. This
    is the only file to change if the SDK surface differs — the ChatModel
    Protocol is stable.
    """

    def __init__(self, endpoint: str, deployment: str, api_version: str) -> None:
        self._endpoint = endpoint
        self._deployment = deployment
        self._api_version = api_version

    def _client(self):
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        from openai import AsyncAzureOpenAI

        token_provider = get_bearer_token_provider(
            DefaultAzureCredential(),
            "https://cognitiveservices.azure.com/.default",
        )
        return AsyncAzureOpenAI(
            azure_endpoint=self._endpoint,
            api_version=self._api_version,
            azure_ad_token_provider=token_provider,
        )

    async def stream_turn(
        self, messages: list[ChatMessage], tools: list[dict[str, Any]]
    ) -> AsyncIterator[ChatModelEvent]:
        client = self._client()
        stream = await client.chat.completions.create(
            model=self._deployment,
            messages=_to_openai(messages),
            tools=tools,
            tool_choice="auto",
            stream=True,
        )
        # accumulate tool-call fragments by index
        calls: dict[int, dict[str, str]] = {}
        finish = "stop"
        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            if delta and delta.content:
                yield TextDelta(text=delta.content)
            if delta and delta.tool_calls:
                for tc in delta.tool_calls:
                    slot = calls.setdefault(tc.index, {"id": "", "name": "", "args": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function and tc.function.name:
                        slot["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        slot["args"] += tc.function.arguments
            if choice.finish_reason:
                finish = choice.finish_reason
        for slot in calls.values():
            if slot["name"]:
                yield ToolCallRequested(
                    id=slot["id"] or "call-0", name=slot["name"],
                    arguments_json=slot["args"] or "{}",
                )
        yield TurnDone(finish_reason=finish)
```

- [ ] **Step 2: Create gated test** `tests/test_azure_openai_integration.py`:
```python
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_AZURE_INTEGRATION") != "1",
    reason="set RUN_AZURE_INTEGRATION=1 + AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_DEPLOYMENT + az login",
)


@pytest.mark.asyncio
async def test_azure_openai_streams_text():
    from continuum_api.agent.azure_openai import AzureOpenAIChatModel
    from continuum_api.agent.types import ChatMessage, TextDelta

    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT")
    if not endpoint or not deployment:
        pytest.skip("AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_DEPLOYMENT not set")

    model = AzureOpenAIChatModel(endpoint, deployment, "2024-10-21")
    msgs = [ChatMessage(role="user", content="Say the single word: ping")]
    text = ""
    async for ev in model.stream_turn(msgs, []):
        if isinstance(ev, TextDelta):
            text += ev.text
    assert text.strip()
```

- [ ] **Step 3: Verify it SKIPS** `cd /home/skkippie/work/continuum/apps/api && uv run python -c "import continuum_api.agent.azure_openai; print('imports-ok')"` → ok; `uv run pytest tests/test_azure_openai_integration.py -v` → 1 skipped. Full suite → all green + skips. `uv run ruff check .` → clean.

- [ ] **Step 4: Commit**
```bash
cd /home/skkippie/work/continuum
git add apps/api/src/continuum_api/agent/azure_openai.py apps/api/tests/test_azure_openai_integration.py
git commit -m "feat(mentor): AzureOpenAIChatModel (streaming tool calls, managed identity) + gated IT

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: BFF chat SSE proxy (web)

**Files:** Create `apps/web/src/app/api/bff/successors/[id]/conversations/route.ts`, `apps/web/src/app/api/bff/conversations/[...path]/route.ts`

Reuse the Spec 1 `forwardToApi(path, init, orgId)` helper in `lib/api.ts` (attaches `X-Service-Token` + `X-Org-Id`) and the session→org resolution pattern from `bff/capture/[...path]/route.ts`. The **message route must stream the SSE body through unbuffered**.

- [ ] **Step 1: Create `apps/web/src/app/api/bff/successors/[id]/conversations/route.ts`** (create-conversation: POST → `/internal/successors/{id}/conversations`):
```typescript
import { headers } from "next/headers";
import { type NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { forwardToApi } from "@/lib/api";

async function org(): Promise<string | null> {
  const session = await auth.api.getSession({ headers: await headers() });
  return session?.user && session.session?.activeOrganizationId
    ? session.session.activeOrganizationId
    : null;
}

export async function POST(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const orgId = await org();
  if (!orgId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { id } = await params;
  try {
    const upstream = await forwardToApi(`successors/${id}/conversations`, { method: "POST" }, orgId);
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json({ error: "upstream_unavailable" }, { status: 503 });
  }
}
```

- [ ] **Step 2: Create `apps/web/src/app/api/bff/conversations/[...path]/route.ts`** (GET history + POST streamed messages):
```typescript
import { headers } from "next/headers";
import { type NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { forwardToApi } from "@/lib/api";

async function org(): Promise<string | null> {
  const session = await auth.api.getSession({ headers: await headers() });
  return session?.user && session.session?.activeOrganizationId
    ? session.session.activeOrganizationId
    : null;
}

async function handle(req: NextRequest, path: string[]): Promise<Response> {
  const orgId = await org();
  if (!orgId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const init: RequestInit = { method: req.method };
  if (req.method !== "GET") init.body = await req.arrayBuffer();
  const contentType = req.headers.get("content-type");
  if (contentType) init.headers = { "content-type": contentType };
  try {
    const upstream = await forwardToApi(`conversations/${path.join("/")}`, init, orgId);
    // Stream the body straight through (SSE). Do NOT await .text()/.json() — that buffers.
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: {
        "content-type": upstream.headers.get("content-type") ?? "application/json",
        "cache-control": "no-cache, no-transform",
        "x-accel-buffering": "no",
      },
    });
  } catch {
    return NextResponse.json({ error: "upstream_unavailable" }, { status: 503 });
  }
}

export async function GET(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return handle(req, (await params).path);
}
export async function POST(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return handle(req, (await params).path);
}
```

- [ ] **Step 3: Verify build + lint** (repo root): `cd /home/skkippie/work/continuum && pnpm --filter web typecheck` → 0; `pnpm check` → clean; `pnpm --filter web build` → green (both routes appear in output). If Biome reformats, accept it.

- [ ] **Step 4: Commit**
```bash
cd /home/skkippie/work/continuum
git add apps/web/src/app/api/bff/successors apps/web/src/app/api/bff/conversations
git commit -m "feat(web): BFF SSE proxy for mentor chat (create conversation + streamed messages)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: Minimal mentor chat UI (web)

**Files:** Create `apps/web/src/lib/chat-sse.ts`, `apps/web/src/components/mentor-chat.tsx`, `apps/web/src/app/chat/[successorId]/page.tsx`

A minimal streaming chat: parse the SSE protocol in the browser, render streamed assistant text + citation chips. (assistant-ui can later wrap this behind the same `lib/chat-sse.ts` parser — out of scope here.)

- [ ] **Step 1: Create `apps/web/src/lib/chat-sse.ts`** — a parser that turns a streamed `Response` body into callbacks:
```typescript
export type Citation = {
  title: string;
  source_document_id: string;
  snippet: string;
  score: number;
};

export type SseHandlers = {
  onDelta: (text: string) => void;
  onRetrieval?: (query: string) => void;
  onCitations: (citations: Citation[]) => void;
  onDone?: (finishReason: string) => void;
  onError?: (detail: string) => void;
};

/** Reads an SSE stream (event:/data: blocks) and dispatches to handlers. */
export async function consumeSse(res: Response, h: SseHandlers): Promise<void> {
  const reader = res.body?.getReader();
  if (!reader) throw new Error("no response body");
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) dispatch(block, h);
  }
  if (buffer.trim()) dispatch(buffer, h);
}

function dispatch(block: string, h: SseHandlers): void {
  let event = "";
  let data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data = line.slice(5).trim();
  }
  if (!event) return;
  if (event === "delta") h.onDelta(JSON.parse(data).text as string);
  else if (event === "retrieval") h.onRetrieval?.(JSON.parse(data).query as string);
  else if (event === "citations") h.onCitations(JSON.parse(data) as Citation[]);
  else if (event === "done") h.onDone?.(JSON.parse(data).finish_reason as string);
  else if (event === "error") h.onError?.(JSON.parse(data).detail as string);
}
```

- [ ] **Step 2: Write a parser unit test** `apps/web/src/lib/chat-sse.test.ts` (this is the one web automated test; run with the web test runner — check `apps/web/package.json` for the test command, likely `vitest`; if no runner is configured, SKIP this step and note it, do not add a test framework just for this):
```typescript
import { describe, expect, it } from "vitest";
import { consumeSse, type Citation } from "./chat-sse";

function sseResponse(raw: string): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(raw));
      controller.close();
    },
  });
  return new Response(stream);
}

describe("consumeSse", () => {
  it("dispatches delta, citations, done in order", async () => {
    const raw =
      'event: delta\ndata: {"text":"Hello "}\n\n' +
      'event: delta\ndata: {"text":"world"}\n\n' +
      'event: citations\ndata: [{"title":"d","source_document_id":"d","snippet":"s","score":1}]\n\n' +
      'event: done\ndata: {"finish_reason":"stop"}\n\n';
    let text = "";
    let cites: Citation[] = [];
    let done = "";
    await consumeSse(sseResponse(raw), {
      onDelta: (t) => { text += t; },
      onCitations: (c) => { cites = c; },
      onDone: (f) => { done = f; },
    });
    expect(text).toBe("Hello world");
    expect(cites[0].source_document_id).toBe("d");
    expect(done).toBe("stop");
  });
});
```

- [ ] **Step 3: Create `apps/web/src/components/mentor-chat.tsx`**:
```tsx
"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { type Citation, consumeSse } from "@/lib/chat-sse";

type Msg = { role: "user" | "assistant"; content: string; citations?: Citation[] };

export function MentorChat({ successorId }: { successorId: string }) {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  async function ensureConversation(): Promise<string> {
    if (conversationId) return conversationId;
    const res = await fetch(`/api/bff/successors/${successorId}/conversations`, { method: "POST" });
    if (!res.ok) throw new Error(`conversation -> ${res.status}`);
    const id = (await res.json()).id as string;
    setConversationId(id);
    return id;
  }

  async function send() {
    if (busy || !input.trim()) return;
    setBusy(true);
    const content = input.trim();
    setInput("");
    setMessages((m) => [...m, { role: "user", content }]);
    setMessages((m) => [...m, { role: "assistant", content: "" }]);
    try {
      const id = await ensureConversation();
      const res = await fetch(`/api/bff/conversations/${id}/messages`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ content }),
      });
      if (!res.ok) throw new Error(`message -> ${res.status}`);
      await consumeSse(res, {
        onDelta: (t) =>
          setMessages((m) => {
            const next = [...m];
            next[next.length - 1] = {
              ...next[next.length - 1],
              content: next[next.length - 1].content + t,
            };
            return next;
          }),
        onCitations: (c) =>
          setMessages((m) => {
            const next = [...m];
            next[next.length - 1] = { ...next[next.length - 1], citations: c };
            return next;
          }),
      });
    } catch (err) {
      setMessages((m) => {
        const next = [...m];
        next[next.length - 1] = {
          role: "assistant",
          content: `ERROR: ${err instanceof Error ? err.message : String(err)}`,
        };
        return next;
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4 p-6">
      <h1 className="text-xl font-semibold">Ask your role's AI successor</h1>
      <div className="flex flex-col gap-3">
        {messages.map((m, i) => (
          <Card key={`${m.role}-${i}`} className="p-3 text-sm">
            <p className="mb-1 text-xs text-muted-foreground">{m.role}</p>
            <p className="whitespace-pre-wrap">{m.content || "…"}</p>
            {m.citations && m.citations.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {m.citations.map((c) => (
                  <span
                    key={`${c.source_document_id}::${c.snippet.slice(0, 24)}`}
                    className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground"
                    title={c.snippet}
                  >
                    {c.source_document_id}
                  </span>
                ))}
              </div>
            )}
          </Card>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          className="flex-1 rounded-md border border-border bg-background px-3 py-2"
          placeholder="Why do we…?"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void send();
          }}
        />
        <Button disabled={busy} onClick={() => void send()}>
          {busy ? "…" : "Ask"}
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create `apps/web/src/app/chat/[successorId]/page.tsx`**:
```tsx
import { MentorChat } from "@/components/mentor-chat";

export default async function ChatPage({
  params,
}: {
  params: Promise<{ successorId: string }>;
}) {
  const { successorId } = await params;
  return <MentorChat successorId={successorId} />;
}
```

- [ ] **Step 5: Verify** (repo root): `cd /home/skkippie/work/continuum && pnpm --filter web typecheck` → 0; `pnpm check` → clean; `pnpm --filter web build` → green (`/chat/[successorId]` appears). If a `vitest` runner exists, `pnpm --filter web test` → the chat-sse test passes; otherwise note that the parser is covered only by build/typecheck.

- [ ] **Step 6: Commit**
```bash
cd /home/skkippie/work/continuum
git add apps/web/src/lib/chat-sse.ts apps/web/src/components/mentor-chat.tsx apps/web/src/app/chat
git commit -m "feat(web): minimal streaming mentor chat (SSE parser + citation chips)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification (run after all tasks)

```bash
docker compose up -d
(cd apps/api && uv run alembic upgrade head && uv run pytest -q)   # all pass; Azure ITs skipped
pnpm --filter web typecheck && pnpm check && pnpm --filter web build
```

## Definition of Done

- Create a conversation for a `ready` Successor → send a question answerable from its Spec 1 docs → the SSE stream emits `delta*` → `citations` → `done`, the citations carry a real `source_document_id`, and the user+assistant messages (with citations) persist + reload.
- An unanswerable question yields an honest "I don't have that in the org's knowledge yet" with **empty citations** (no hallucination).
- The whole loop runs on `chat_backend=fake` + `knowledge_backend=fake` with **no Azure**; flips to real by setting `chat_backend=azure_openai` + the Azure OpenAI endpoint/deployment. Real model verified by the gated `@integration` test.
- Browser → BFF (SSE streamed through, unbuffered) → FastAPI → agent → retrieval → back; the browser never calls FastAPI directly. Cross-org conversation access → 404.
- `conversation` + `message` are Alembic-owned, in `_MANAGED_TABLES`; the 7 Better Auth tables remain intact.

## Notes for the implementer

- **Reuse, don't reinvent**: `require_service_token`, `_org`, `successor_in_org` (Spec 1), and `forwardToApi` (web `lib/api.ts`). The fake knowledge singleton + autouse `_reset_fake_knowledge` fixture from Spec 1 mean each test starts clean; the chat API test drives the Spec 1 capture loop first so the same-process fake holds the indexed doc.
- **The riskiest seam is two-hop SSE streaming** (FastAPI → Next BFF → browser). Verify the BFF route streams unbuffered (Task 12): never call `.text()`/`.json()` on the upstream — pass `upstream.body` through. Manually smoke it once services are up before trusting it.
- **`agent-framework` is intentionally NOT used** for the single-tool loop (see Architecture decision #1). If a later phase needs multi-agent orchestration, wrap it behind `ChatModel`.
- **assistant-ui** can replace `mentor-chat.tsx` later, consuming the same `consumeSse` parser + SSE protocol — no API change needed.
- Never `alembic revision --autogenerate`. New tables → `_MANAGED_TABLES` + hand-written migration.
