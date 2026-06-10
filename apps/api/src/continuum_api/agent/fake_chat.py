import json
from collections.abc import AsyncIterator

from continuum_api.agent.types import (
    ChatMessage,
    ChatModelEvent,
    TextDelta,
    ToolCallRequested,
    TurnDone,
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
                id="fake-call-1",
                name="retrieve",
                arguments_json=json.dumps({"query": last_user}),
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
