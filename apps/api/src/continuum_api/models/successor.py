from datetime import datetime

from sqlmodel import Field, SQLModel


class Successor(SQLModel, table=True):
    __tablename__ = "successor"

    id: str = Field(primary_key=True)
    role_id: str = Field(unique=True, index=True)
    knowledge_base_name: str
    status: str = Field(default="provisioning")  # provisioning | ready | failed
    summary: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
