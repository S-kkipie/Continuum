from datetime import datetime

from sqlmodel import Field, SQLModel


class IngestionJob(SQLModel, table=True):
    __tablename__ = "ingestion_job"

    id: str = Field(primary_key=True)
    successor_id: str = Field(index=True)
    status: str = Field(default="queued")  # queued | running | succeeded | partial | failed
    run_ref: str = Field(default="")
    doc_total: int = 0
    doc_indexed: int = 0
    doc_failed: int = 0
    error: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
