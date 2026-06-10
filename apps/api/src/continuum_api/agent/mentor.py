import asyncio
import json
from collections.abc import AsyncGenerator

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
        # Persisted history is user/assistant text only; prior tool-call turns are
        # collapsed to the assistant's final text (intentional simplification for v1).
        out: list[ChatMessage] = []
        for m in history:
            if m.role in ("user", "assistant"):
                out.append(ChatMessage(role=m.role, content=m.content))
        return out

    async def stream(
        self, history: list[Message], user_message: str
    ) -> AsyncGenerator[MentorEvent, None]:
        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=build_system_prompt(self._role, self._successor)),
            *self._history_to_messages(history),
            ChatMessage(role="user", content=user_message),
        ]
        used: list[RetrievedSnippet] = []
        finish = "stop"

        for _ in range(self._max_iter):
            # (id, query, arguments_json)
            tool_calls_this_turn: list[tuple[str, str, str]] = []
            assistant_text = ""
            turn_finish = "stop"
            async for ev in self._chat.stream_turn(messages, [RETRIEVE_TOOL]):
                if isinstance(ev, TextDelta):
                    assistant_text += ev.text
                    yield ev
                elif isinstance(ev, ToolCallRequested) and ev.name == "retrieve":
                    query = _parse_query(ev.arguments_json)
                    tool_calls_this_turn.append((ev.id, query, ev.arguments_json))
                elif isinstance(ev, TurnDone):
                    turn_finish = ev.finish_reason

            if not tool_calls_this_turn:
                finish = turn_finish
                break

            messages.append(
                ChatMessage(
                    role="assistant",
                    content=assistant_text,
                    tool_calls=[
                        {"id": cid, "name": "retrieve", "arguments": args_json}
                        for cid, _query, args_json in tool_calls_this_turn
                    ],
                )
            )
            for cid, query, _args in tool_calls_this_turn:
                yield RetrievalStarted(query=query)
                snippets = await asyncio.to_thread(
                    self._kn.retrieve,
                    self._successor.knowledge_base_name,
                    query,
                    top=self._top,
                )
                used.extend(snippets)
                messages.append(
                    ChatMessage(
                        role="tool",
                        tool_call_id=cid,
                        content="\n\n".join(s.content for s in snippets),
                    )
                )
        else:
            finish = "max_iterations"

        yield Citations(
            items=[
                Citation(
                    title=s.title,
                    source_document_id=s.source_document_id,
                    snippet=s.content,
                    score=s.score,
                )
                for s in _dedupe(used)
            ]
        )
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
