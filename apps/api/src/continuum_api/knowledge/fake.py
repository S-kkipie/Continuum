from dataclasses import dataclass, field

from continuum_api.knowledge.interface import BlobStore
from continuum_api.knowledge.types import IndexingStatus, RetrievedSnippet

_STRIP = ".,!?;:()[]\"'-"


@dataclass
class _Chunk:
    text: str
    source_document_id: str


@dataclass
class _Kb:
    container: str | None = None
    chunks: list[_Chunk] = field(default_factory=list)


def _words(text: str) -> set[str]:
    return {w.strip(_STRIP).lower() for w in text.split() if w.strip(_STRIP)}


def _overlap(query_words: set[str], chunk_words: set[str]) -> int:
    """Count matching terms, treating prefix matches (≥4 chars) as hits.

    This lets ``deploy`` match ``deploys``, ``refund`` match ``refunds``, etc.,
    without a full stemmer dependency.
    """
    exact = len(query_words & chunk_words)
    prefix = sum(
        1
        for q in query_words - chunk_words
        for c in chunk_words
        if len(q) >= 4 and (c.startswith(q) or q.startswith(c))
    )
    return exact + prefix


class FakeFoundryKnowledge:
    """In-memory FoundryKnowledge: reads text blobs, keyword-scores chunks.

    Each indexing run gets an immutable status snapshot keyed by run id, so a
    re-index of the same kb never rewrites an earlier run's reported status.
    """

    def __init__(self, blob: BlobStore) -> None:
        self._blob = blob
        self._kbs: dict[str, _Kb] = {}
        self._run_status: dict[str, IndexingStatus] = {}  # run_id -> snapshot

    def ensure_knowledge_base(self, name: str) -> str:
        self._kbs.setdefault(name, _Kb())
        return name

    def ensure_blob_source(self, kb: str, container: str) -> str:
        self._kbs[kb].container = container
        return f"{kb}::{container}"

    def start_indexing(self, kb: str) -> str:
        state = self._kbs[kb]
        if state.container is None:
            raise RuntimeError(
                f"no blob source registered for kb '{kb}'; call ensure_blob_source first"
            )
        state.chunks.clear()
        indexed = failed = 0
        errors: list[str] = []
        for path in self._blob.list_paths(state.container):
            try:
                text = self._blob.read(state.container, path).decode("utf-8")
            except UnicodeDecodeError:
                failed += 1
                errors.append(f"{path}: not utf-8 text")
                continue
            for para in (p.strip() for p in text.split("\n\n") if p.strip()):
                state.chunks.append(_Chunk(text=para, source_document_id=path))
            indexed += 1
        if failed and indexed:
            result = "partial"
        elif failed and not indexed:
            result = "failed"
        else:
            result = "succeeded"
        run_id = f"run-{kb}-{len(self._run_status)}"
        self._run_status[run_id] = IndexingStatus(
            state=result, indexed=indexed, failed=failed, errors=errors
        )
        return run_id

    def indexing_status(self, run: str) -> IndexingStatus:
        return self._run_status[run]

    def retrieve(self, kb: str, query: str, *, top: int = 5) -> list[RetrievedSnippet]:
        q = _words(query)
        scored: list[RetrievedSnippet] = []
        for chunk in self._kbs[kb].chunks:
            overlap = _overlap(q, _words(chunk.text))
            if overlap:
                scored.append(
                    RetrievedSnippet(
                        content=chunk.text,
                        title=chunk.source_document_id,
                        source_document_id=chunk.source_document_id,
                        score=float(overlap),
                    )
                )
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:top]
