from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievedSnippet:
    content: str
    title: str
    source_document_id: str
    score: float


@dataclass(frozen=True)
class IndexingStatus:
    state: str  # running | succeeded | partial | failed
    indexed: int
    failed: int
    errors: list[str]
