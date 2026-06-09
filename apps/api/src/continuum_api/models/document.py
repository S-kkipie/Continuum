from datetime import datetime

from sqlmodel import Field, SQLModel


class Document(SQLModel, table=True):
    __tablename__ = "document"

    id: str = Field(primary_key=True)
    source_id: str = Field(index=True)
    filename: str
    content_type: str
    blob_path: str
    size_bytes: int
    status: str = Field(default="uploaded")  # uploaded | indexing | indexed | failed
    error: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
