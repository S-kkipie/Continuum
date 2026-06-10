import pytest

from continuum_api.agent.fake_chat import FakeChatModel
from continuum_api.agent.mentor import MentorAgent
from continuum_api.agent.types import (
    Citations,
    MentorDone,
    TextDelta,
    ToolCallRequested,
    TurnDone,
)
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
    assert "RetrievalStarted" in kinds
    assert kinds.index("Citations") < kinds.index("MentorDone")
    last_delta = max((i for i, k in enumerate(kinds) if k == "TextDelta"), default=-1)
    assert last_delta < kinds.index("Citations")
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


class _AlwaysToolModel:
    async def stream_turn(self, messages, tools):
        yield ToolCallRequested(id="t", name="retrieve", arguments_json='{"query": "x"}')
        yield TurnDone(finish_reason="tool_calls")


@pytest.mark.asyncio
async def test_loop_stops_at_max_iterations(tmp_path):
    kn = _knowledge(tmp_path, "We deploy on Fridays.")
    role = Role(id="r1", org_id="o1", title="Support Lead")
    successor = Successor(id="s1", role_id="r1", knowledge_base_name="kb")
    agent = MentorAgent(_AlwaysToolModel(), kn, role, successor, max_iterations=3)
    events = await _collect(agent.stream([], "loop forever"))
    assert isinstance(events[-1], MentorDone)
    assert events[-1].finish_reason == "max_iterations"
