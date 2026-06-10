from datetime import datetime

from sqlmodel import Field, SQLModel


class Conversation(SQLModel, table=True):
    __tablename__ = "conversation"

    id: str = Field(primary_key=True)
    successor_id: str = Field(index=True)
    user_id: str = Field(index=True)  # Better Auth user id (no cross-ORM FK)
    title: str = Field(default="")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # set by ConversationService on append (no ORM onupdate hook)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
