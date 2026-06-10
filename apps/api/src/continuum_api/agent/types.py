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
