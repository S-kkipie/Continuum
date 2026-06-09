from datetime import datetime

from sqlmodel import Field, SQLModel


class Role(SQLModel, table=True):
    __tablename__ = "role"

    id: str = Field(primary_key=True)
    org_id: str = Field(index=True)
    title: str
    description: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
