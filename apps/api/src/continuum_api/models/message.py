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
