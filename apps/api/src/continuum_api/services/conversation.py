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
        self,
        conversation_id: str,
        *,
        role: str,
        content: str,
        citations: list[dict[str, Any]] | None = None,
    ) -> Message:
        convo = self.conversations.get(conversation_id)
        if convo is None:
            raise LookupError("conversation not found")
        msg = self.messages.create(Message(
            id=_id("msg"), conversation_id=conversation_id, role=role,
            content=content, citations=citations,
        ))
        convo.updated_at = datetime.utcnow()
        if not convo.title and role == "user":
            convo.title = content[:_TITLE_MAX]
        self._s.flush()
        return msg
