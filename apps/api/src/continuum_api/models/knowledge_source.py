from datetime import datetime

from sqlmodel import Field, SQLModel


class KnowledgeSource(SQLModel, table=True):
    __tablename__ = "knowledge_source"

    id: str = Field(primary_key=True)
    successor_id: str = Field(index=True)
    type: str = Field(default="blob")  # blob (only type in v1)
    container: str
    status: str = Field(default="created")
    created_at: datetime = Field(default_factory=datetime.utcnow)
