from collections.abc import AsyncIterator
from typing import Any, Protocol

from continuum_api.agent.types import ChatMessage, ChatModelEvent


class ChatModel(Protocol):
    def stream_turn(
        self, messages: list[ChatMessage], tools: list[dict[str, Any]]
    ) -> AsyncIterator[ChatModelEvent]:
        """Stream one model turn.

        Implementations are `async def` generators (`async def stream_turn(...): ... yield`),
        so calling this returns an async iterator synchronously — do NOT `await` the call;
        `async for ev in model.stream_turn(...)`.
        """
        ...
