import pytest

from continuum_api.agent.fake_chat import FakeChatModel
from continuum_api.agent.types import (
    RETRIEVE_TOOL,
    ChatMessage,
    TextDelta,
    ToolCallRequested,
    TurnDone,
)


async def _collect(aiter):
    return [e async for e in aiter]


@pytest.mark.asyncio
async def test_first_turn_requests_retrieve():
    model = FakeChatModel()
    msgs = [
        ChatMessage(role="system", content="..."),
        ChatMessage(role="user", content="why do we deploy on fridays?"),
    ]
    events = await _collect(model.stream_turn(msgs, [RETRIEVE_TOOL]))
    assert any(isinstance(e, ToolCallRequested) and e.name == "retrieve" for e in events)
    assert isinstance(events[-1], TurnDone) and events[-1].finish_reason == "tool_calls"


@pytest.mark.asyncio
async def test_second_turn_answers_from_tool_content():
    model = FakeChatModel()
    msgs = [
        ChatMessage(role="user", content="why fridays?"),
        ChatMessage(
            role="assistant",
            content="",
            tool_calls=[{"id": "t1", "name": "retrieve"}],
        ),
        ChatMessage(
            role="tool",
            tool_call_id="t1",
            content="We deploy on Fridays to avoid mid-week risk.",
        ),
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
        ChatMessage(
            role="assistant",
            content="",
            tool_calls=[{"id": "t1", "name": "retrieve"}],
        ),
        ChatMessage(role="tool", tool_call_id="t1", content=""),
    ]
    events = await _collect(model.stream_turn(msgs, [RETRIEVE_TOOL]))
    text = "".join(e.text for e in events if isinstance(e, TextDelta)).lower()
    assert "don't have" in text or "do not have" in text
