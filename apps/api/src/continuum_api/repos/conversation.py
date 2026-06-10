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
