# Spec 1 — Capture Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest organizational documents for a Role and turn them into a queryable Successor backed by a knowledge base, so an agent (Spec 2) can `retrieve` grounded snippets with citations.

**Architecture:** All in `apps/api` (FastAPI + SQLModel + Alembic). Two swappable abstractions — `BlobStore` (document bytes) and `FoundryKnowledge` (index + retrieve) — each with a dev/test implementation (`LocalBlobStore`, `FakeFoundryKnowledge`) and a real Azure implementation (`AzureBlobStore`, `FoundryKnowledgeClient`), chosen by settings. `IngestionService` orchestrates: store → register source → index → track job → set Successor status. A thin web admin slice (BFF + page) makes the loop observable.

**Tech Stack:** FastAPI, SQLModel, Alembic, pydantic-settings, azure-storage-blob, azure-search-documents, azure-identity (Python); Next.js BFF + TanStack Query (web). Defaults: `blob_backend=local`, `knowledge_backend=fake` (no Azure needed for dev/CI). Real Azure verified via `@integration` tests only.

**Conventions:** Commands run from `apps/api` unless noted. Append to every commit message: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. NEVER run `alembic revision --autogenerate` — hand-write migrations and add new tables to `_MANAGED_TABLES` (see `apps/api/AGENTS.md`). All TS lint is Biome (`pnpm check`), Python is ruff.

---

## File Structure

```
apps/api/src/continuum_api/
├── settings.py                      # +capture settings (backends, paths, azure config)
├── models/
│   ├── role.py  successor.py  knowledge_source.py  document.py  ingestion_job.py
│   └── __init__.py                  # export all + (used by alembic _MANAGED_TABLES)
├── knowledge/
│   ├── __init__.py
│   ├── types.py                     # RetrievedSnippet + ref types
│   ├── interface.py                 # FoundryKnowledge Protocol + BlobStore Protocol
│   ├── fake.py                      # FakeFoundryKnowledge (in-memory keyword retrieval)
│   ├── local_blob.py                # LocalBlobStore (filesystem)
│   ├── azure_blob.py                # AzureBlobStore (azure-storage-blob)
│   ├── foundry.py                   # FoundryKnowledgeClient (azure-search-documents)
│   └── factory.py                   # settings-driven build_blob_store() / build_knowledge()
├── repos/capture.py                 # SQLModel repositories for the 5 entities
├── services/ingestion.py           # IngestionService (orchestration + state machine)
├── routes/capture.py                # FastAPI endpoints + DTOs
alembic/versions/0002_capture.py     # the 5 capture tables
apps/web/src/app/api/bff/capture/... # BFF proxy routes
apps/web/src/app/admin/page.tsx      # minimal admin UI
```

---

## Task 1: Capture dependencies + settings

**Files:** Modify `apps/api/pyproject.toml`, `apps/api/src/continuum_api/settings.py`

- [ ] **Step 1: Add deps to `pyproject.toml`** `[project.dependencies]` (keep existing): add `"azure-storage-blob>=12.23"`, `"azure-search-documents>=11.6"`. Then run `uv sync`. Expected: resolves, `uv.lock` updates.

- [ ] **Step 2: Extend `settings.py`** — add capture config (keep existing fields):

```python
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_ENV = Path(__file__).parents[4] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ROOT_ENV), extra="ignore")

    database_url: str = "postgresql://continuum:continuum@localhost:5432/continuum"
    api_service_token: str

    # Capture backends — default to local/fake so the loop runs without Azure.
    blob_backend: Literal["local", "azure"] = "local"
    knowledge_backend: Literal["fake", "foundry"] = "fake"
    blob_local_root: str = ".data/blobs"

    # Azure (only used when the backends above are azure/foundry)
    azure_storage_account_url: str = ""
    azure_search_endpoint: str = ""

    # Retrieval tuning
    retrieve_top: int = 5


settings = Settings()
```

- [ ] **Step 3: Verify** `uv run python -c "from continuum_api.settings import settings; print(settings.blob_backend, settings.knowledge_backend)"` → prints `local fake`. Then `uv run ruff check .` → clean.

- [ ] **Step 4: Add `.data/` to gitignore** — append `.data/` to the repo-root `.gitignore` (local blob storage must not be committed). Verify `git check-ignore apps/api/.data` ... actually the path is relative to where the api runs; add both `.data/` to root `.gitignore`.

- [ ] **Step 5: Commit**
```bash
git add apps/api/pyproject.toml apps/api/uv.lock apps/api/src/continuum_api/settings.py ../../.gitignore
git commit -m "feat(capture): add blob/search deps + backend settings (local/fake defaults)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Domain models

**Files:** Create `models/{role,successor,knowledge_source,document,ingestion_job}.py`; modify `models/__init__.py`

- [ ] **Step 1: Write the failing test** `tests/test_models_capture.py`:
```python
from continuum_api.models import (
    Document, IngestionJob, KnowledgeSource, Role, Successor,
)


def test_capture_models_have_expected_tablenames():
    assert Role.__tablename__ == "role"
    assert Successor.__tablename__ == "successor"
    assert KnowledgeSource.__tablename__ == "knowledge_source"
    assert Document.__tablename__ == "document"
    assert IngestionJob.__tablename__ == "ingestion_job"


def test_successor_status_defaults_to_provisioning():
    s = Successor(role_id="r1", knowledge_base_name="kb-o1-r1")
    assert s.status == "provisioning"
```

- [ ] **Step 2: Run, confirm fail** `uv run pytest tests/test_models_capture.py -v` → ImportError (models absent).

- [ ] **Step 3: Create `models/role.py`**:
```python
from datetime import datetime

from sqlmodel import Field, SQLModel


class Role(SQLModel, table=True):
    __tablename__ = "role"

    id: str = Field(primary_key=True)
    org_id: str = Field(index=True)
    title: str
    description: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

- [ ] **Step 4: Create `models/successor.py`**:
```python
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
```

- [ ] **Step 5: Create `models/knowledge_source.py`**:
```python
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
```

- [ ] **Step 6: Create `models/document.py`**:
```python
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
```

- [ ] **Step 7: Create `models/ingestion_job.py`**:
```python
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
```

- [ ] **Step 8: Update `models/__init__.py`**:
```python
from continuum_api.models.app_info import AppInfo
from continuum_api.models.document import Document
from continuum_api.models.ingestion_job import IngestionJob
from continuum_api.models.knowledge_source import KnowledgeSource
from continuum_api.models.role import Role
from continuum_api.models.successor import Successor

__all__ = [
    "AppInfo",
    "Document",
    "IngestionJob",
    "KnowledgeSource",
    "Role",
    "Successor",
]
```

- [ ] **Step 9: Run, confirm pass** `uv run pytest tests/test_models_capture.py -v` → 2 passed. `uv run ruff check .` → clean.

- [ ] **Step 10: Commit**
```bash
git add apps/api/src/continuum_api/models apps/api/tests/test_models_capture.py
git commit -m "feat(capture): Role/Successor/KnowledgeSource/Document/IngestionJob models

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Alembic migration for the capture tables

**Files:** Create `alembic/versions/0002_capture.py`; modify `alembic/env.py` (`_MANAGED_TABLES`)

- [ ] **Step 1: Add the new tables to `_MANAGED_TABLES`** in `alembic/env.py`:
```python
_MANAGED_TABLES = {
    "app_info",
    "role",
    "successor",
    "knowledge_source",
    "document",
    "ingestion_job",
}
```

- [ ] **Step 2: Hand-write `alembic/versions/0002_capture.py`**:
```python
"""capture: role, successor, knowledge_source, document, ingestion_job"""
import sqlalchemy as sa
from alembic import op

revision = "0002_capture"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "role",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("org_id", sa.String, nullable=False, index=True),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("description", sa.String, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "successor",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("role_id", sa.String, nullable=False, unique=True, index=True),
        sa.Column("knowledge_base_name", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="provisioning"),
        sa.Column("summary", sa.String, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "knowledge_source",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("successor_id", sa.String, nullable=False, index=True),
        sa.Column("type", sa.String, nullable=False, server_default="blob"),
        sa.Column("container", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="created"),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "document",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("source_id", sa.String, nullable=False, index=True),
        sa.Column("filename", sa.String, nullable=False),
        sa.Column("content_type", sa.String, nullable=False),
        sa.Column("blob_path", sa.String, nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="uploaded"),
        sa.Column("error", sa.String, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "ingestion_job",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("successor_id", sa.String, nullable=False, index=True),
        sa.Column("status", sa.String, nullable=False, server_default="queued"),
        sa.Column("run_ref", sa.String, nullable=False, server_default=""),
        sa.Column("doc_total", sa.Integer, nullable=False, server_default="0"),
        sa.Column("doc_indexed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("doc_failed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.String, nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ingestion_job")
    op.drop_table("document")
    op.drop_table("knowledge_source")
    op.drop_table("successor")
    op.drop_table("role")
```

- [ ] **Step 3: Apply + verify coexistence** (Postgres up):
```bash
uv run alembic upgrade head
docker compose -f ../../docker-compose.yml exec -T postgres psql -U continuum -d continuum -c "\dt"
```
Expected: lists the 7 Better Auth tables + `app_info` + the 5 new capture tables + `alembic_version`. (If any Better Auth table is gone you ran autogenerate by mistake — STOP.)

- [ ] **Step 4: Confirm tests still green** `uv run pytest -q` → all pass. `uv run ruff check .` → clean.

- [ ] **Step 5: Commit**
```bash
git add apps/api/alembic
git commit -m "feat(capture): alembic 0002 creates capture tables (Better Auth tables intact)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Knowledge + blob interfaces and types

**Files:** Create `knowledge/__init__.py`, `knowledge/types.py`, `knowledge/interface.py`

- [ ] **Step 1: Create `knowledge/types.py`**:
```python
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
```

- [ ] **Step 2: Create `knowledge/interface.py`** (Protocols — the swap points):
```python
from typing import Protocol

from continuum_api.knowledge.types import IndexingStatus, RetrievedSnippet


class BlobStore(Protocol):
    def ensure_container(self, successor_id: str) -> str: ...
    def put(self, container: str, filename: str, data: bytes, content_type: str) -> str: ...
    def list_paths(self, container: str) -> list[str]: ...
    def read(self, container: str, blob_path: str) -> bytes: ...


class FoundryKnowledge(Protocol):
    def ensure_knowledge_base(self, name: str) -> str: ...
    def ensure_blob_source(self, kb: str, container: str) -> str: ...
    def start_indexing(self, kb: str) -> str: ...
    def indexing_status(self, run: str) -> IndexingStatus: ...
    def retrieve(self, kb: str, query: str, *, top: int = 5) -> list[RetrievedSnippet]: ...
```

- [ ] **Step 3: Create empty `knowledge/__init__.py`**:
```python
# knowledge package
```

- [ ] **Step 4: Verify import** `uv run python -c "from continuum_api.knowledge.interface import BlobStore, FoundryKnowledge; print('ok')"` → `ok`. `uv run ruff check .` → clean.

- [ ] **Step 5: Commit**
```bash
git add apps/api/src/continuum_api/knowledge
git commit -m "feat(capture): BlobStore + FoundryKnowledge protocols + types

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: LocalBlobStore (filesystem) — TDD

**Files:** Create `knowledge/local_blob.py`, `tests/test_local_blob.py`

- [ ] **Step 1: Write failing test** `tests/test_local_blob.py`:
```python
from pathlib import Path

from continuum_api.knowledge.local_blob import LocalBlobStore


def test_put_read_list_roundtrip(tmp_path: Path):
    store = LocalBlobStore(root=str(tmp_path))
    container = store.ensure_container("succ-1")
    path = store.put(container, "a.txt", b"hello world", "text/plain")
    assert store.read(container, path) == b"hello world"
    assert path in store.list_paths(container)


def test_containers_are_isolated(tmp_path: Path):
    store = LocalBlobStore(root=str(tmp_path))
    c1 = store.ensure_container("s1")
    c2 = store.ensure_container("s2")
    store.put(c1, "x.txt", b"one", "text/plain")
    assert store.list_paths(c2) == []
```

- [ ] **Step 2: Run, confirm fail** `uv run pytest tests/test_local_blob.py -v` → ImportError.

- [ ] **Step 3: Create `knowledge/local_blob.py`**:
```python
from pathlib import Path


class LocalBlobStore:
    def __init__(self, root: str) -> None:
        self._root = Path(root)

    def ensure_container(self, successor_id: str) -> str:
        container = f"continuum-{successor_id}"
        (self._root / container).mkdir(parents=True, exist_ok=True)
        return container

    def put(self, container: str, filename: str, data: bytes, content_type: str) -> str:
        target = self._root / container / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return filename

    def list_paths(self, container: str) -> list[str]:
        base = self._root / container
        if not base.exists():
            return []
        return sorted(p.name for p in base.iterdir() if p.is_file())

    def read(self, container: str, blob_path: str) -> bytes:
        return (self._root / container / blob_path).read_bytes()
```

- [ ] **Step 4: Run, confirm pass** `uv run pytest tests/test_local_blob.py -v` → 2 passed. `uv run ruff check .` → clean.

- [ ] **Step 5: Commit**
```bash
git add apps/api/src/continuum_api/knowledge/local_blob.py apps/api/tests/test_local_blob.py
git commit -m "feat(capture): LocalBlobStore (filesystem backend)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: FakeFoundryKnowledge (in-memory keyword retrieval) — TDD

**Files:** Create `knowledge/fake.py`, `tests/test_fake_knowledge.py`

The fake mimics native cracking: on `start_indexing` it reads the source container's blobs (utf-8 text; binary skipped), splits each into paragraph chunks, and `retrieve` scores chunks by case-insensitive query-word overlap.

- [ ] **Step 1: Write failing test** `tests/test_fake_knowledge.py`:
```python
from continuum_api.knowledge.fake import FakeFoundryKnowledge
from continuum_api.knowledge.local_blob import LocalBlobStore


def _setup(tmp_path):
    blob = LocalBlobStore(root=str(tmp_path))
    container = blob.ensure_container("s1")
    blob.put(container, "onboarding.txt",
             b"We deploy on Fridays.\n\nRefunds require manager approval.", "text/plain")
    kn = FakeFoundryKnowledge(blob)
    kb = kn.ensure_knowledge_base("kb-o1-r1")
    kn.ensure_blob_source(kb, container)
    run = kn.start_indexing(kb)
    return kn, kb, run


def test_indexing_status_succeeds(tmp_path):
    kn, kb, run = _setup(tmp_path)
    status = kn.indexing_status(run)
    assert status.state == "succeeded"
    assert status.indexed == 1


def test_retrieve_returns_relevant_snippet_with_citation(tmp_path):
    kn, kb, _ = _setup(tmp_path)
    hits = kn.retrieve(kb, "refund approval", top=3)
    assert hits, "expected at least one hit"
    assert "Refunds" in hits[0].content
    assert hits[0].source_document_id == "onboarding.txt"


def test_retrieve_empty_when_no_overlap(tmp_path):
    kn, kb, _ = _setup(tmp_path)
    assert kn.retrieve(kb, "quantum chromodynamics", top=3) == []
```

- [ ] **Step 2: Run, confirm fail** `uv run pytest tests/test_fake_knowledge.py -v` → ImportError.

- [ ] **Step 3: Create `knowledge/fake.py`**:
```python
from dataclasses import dataclass, field

from continuum_api.knowledge.interface import BlobStore
from continuum_api.knowledge.types import IndexingStatus, RetrievedSnippet


@dataclass
class _Chunk:
    text: str
    source_document_id: str


@dataclass
class _Kb:
    container: str | None = None
    chunks: list[_Chunk] = field(default_factory=list)
    indexed: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


def _words(text: str) -> set[str]:
    return {w.strip(".,!?;:").lower() for w in text.split() if w.strip(".,!?;:")}


class FakeFoundryKnowledge:
    """In-memory FoundryKnowledge: reads text blobs, keyword-scores chunks."""

    def __init__(self, blob: BlobStore) -> None:
        self._blob = blob
        self._kbs: dict[str, _Kb] = {}
        self._runs: dict[str, str] = {}  # run_id -> kb

    def ensure_knowledge_base(self, name: str) -> str:
        self._kbs.setdefault(name, _Kb())
        return name

    def ensure_blob_source(self, kb: str, container: str) -> str:
        self._kbs[kb].container = container
        return f"{kb}::{container}"

    def start_indexing(self, kb: str) -> str:
        state = self._kbs[kb]
        state.chunks.clear()
        state.indexed = state.failed = 0
        state.errors.clear()
        for path in self._blob.list_paths(state.container or ""):
            try:
                text = self._blob.read(state.container, path).decode("utf-8")
            except UnicodeDecodeError:
                state.failed += 1
                state.errors.append(f"{path}: not utf-8 text")
                continue
            for para in (p.strip() for p in text.split("\n\n") if p.strip()):
                state.chunks.append(_Chunk(text=para, source_document_id=path))
            state.indexed += 1
        run_id = f"run-{kb}-{len(self._runs)}"
        self._runs[run_id] = kb
        return run_id

    def indexing_status(self, run: str) -> IndexingStatus:
        state = self._kbs[self._runs[run]]
        result = "succeeded"
        if state.failed and state.indexed:
            result = "partial"
        elif state.failed and not state.indexed:
            result = "failed"
        return IndexingStatus(
            state=result, indexed=state.indexed, failed=state.failed, errors=list(state.errors)
        )

    def retrieve(self, kb: str, query: str, *, top: int = 5) -> list[RetrievedSnippet]:
        q = _words(query)
        scored: list[RetrievedSnippet] = []
        for chunk in self._kbs[kb].chunks:
            overlap = len(q & _words(chunk.text))
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
```

- [ ] **Step 4: Run, confirm pass** `uv run pytest tests/test_fake_knowledge.py -v` → 3 passed. `uv run ruff check .` → clean.

- [ ] **Step 5: Commit**
```bash
git add apps/api/src/continuum_api/knowledge/fake.py apps/api/tests/test_fake_knowledge.py
git commit -m "feat(capture): FakeFoundryKnowledge (in-memory keyword retrieval)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Repositories — TDD

**Files:** Create `repos/__init__.py`, `repos/capture.py`, `tests/test_capture_repos.py`

- [ ] **Step 1: Write failing test** `tests/test_capture_repos.py`:
```python
from sqlmodel import Session

from continuum_api.db import engine
from continuum_api.models import Role
from continuum_api.repos.capture import RoleRepo


def test_role_repo_create_and_get():
    with Session(engine) as s:
        repo = RoleRepo(s)
        role = repo.create(Role(id="r-test-1", org_id="o1", title="Backend Eng"))
        s.commit()
        fetched = repo.get("r-test-1")
        assert fetched is not None
        assert fetched.title == "Backend Eng"
```

- [ ] **Step 2: Run, confirm fail** `uv run pytest tests/test_capture_repos.py -v` → ImportError.

- [ ] **Step 3: Create `repos/__init__.py`** (`# repos package`) and `repos/capture.py`:
```python
from sqlmodel import Session, select

from continuum_api.models import (
    Document, IngestionJob, KnowledgeSource, Role, Successor,
)


class RoleRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, role: Role) -> Role:
        self._s.add(role)
        return role

    def get(self, role_id: str) -> Role | None:
        return self._s.get(Role, role_id)

    def list_by_org(self, org_id: str) -> list[Role]:
        return list(self._s.exec(select(Role).where(Role.org_id == org_id)))


class SuccessorRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, successor: Successor) -> Successor:
        self._s.add(successor)
        return successor

    def get(self, successor_id: str) -> Successor | None:
        return self._s.get(Successor, successor_id)

    def by_role(self, role_id: str) -> Successor | None:
        return self._s.exec(select(Successor).where(Successor.role_id == role_id)).first()


class KnowledgeSourceRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, source: KnowledgeSource) -> KnowledgeSource:
        self._s.add(source)
        return source

    def for_successor(self, successor_id: str) -> KnowledgeSource | None:
        return self._s.exec(
            select(KnowledgeSource).where(KnowledgeSource.successor_id == successor_id)
        ).first()


class DocumentRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, doc: Document) -> Document:
        self._s.add(doc)
        return doc

    def for_source(self, source_id: str) -> list[Document]:
        return list(self._s.exec(select(Document).where(Document.source_id == source_id)))


class IngestionJobRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, job: IngestionJob) -> IngestionJob:
        self._s.add(job)
        return job

    def get(self, job_id: str) -> IngestionJob | None:
        return self._s.get(IngestionJob, job_id)
```

- [ ] **Step 4: Run, confirm pass** `uv run pytest tests/test_capture_repos.py -v` → 1 passed (needs Postgres + migration applied). `uv run ruff check .` → clean.

- [ ] **Step 5: Commit**
```bash
git add apps/api/src/continuum_api/repos apps/api/tests/test_capture_repos.py
git commit -m "feat(capture): SQLModel repositories for capture entities

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: IngestionService (orchestration) — TDD against fakes

**Files:** Create `services/__init__.py`, `services/ingestion.py`, `tests/test_ingestion_service.py`

`IngestionService` owns the state machine: provision KB on successor create, store uploaded docs, then ingest (ensure source → start_indexing → reconcile per-doc + job + successor.status). It takes a `Session`, a `BlobStore`, and a `FoundryKnowledge` (injected → testable with fakes).

- [ ] **Step 1: Write failing test** `tests/test_ingestion_service.py`:
```python
import uuid

from sqlmodel import Session

from continuum_api.db import engine
from continuum_api.knowledge.fake import FakeFoundryKnowledge
from continuum_api.knowledge.local_blob import LocalBlobStore
from continuum_api.services.ingestion import IngestionService


def _svc(tmp_path):
    session = Session(engine)
    blob = LocalBlobStore(root=str(tmp_path))
    knowledge = FakeFoundryKnowledge(blob)
    return IngestionService(session, blob, knowledge), session


def test_full_capture_loop_sets_successor_ready(tmp_path):
    svc, session = _svc(tmp_path)
    org, role = f"o-{uuid.uuid4().hex[:8]}", f"r-{uuid.uuid4().hex[:8]}"
    svc.create_role(role_id=role, org_id=org, title="Support Lead")
    successor = svc.create_successor(role_id=role, org_id=org)
    svc.add_documents(successor.id, [("policy.txt", b"Refunds need manager approval.", "text/plain")])
    job = svc.ingest(successor.id)
    job = svc.sync_job(job.id)
    session.commit()

    assert job.status == "succeeded"
    assert job.doc_indexed == 1
    refreshed = svc.get_successor(successor.id)
    assert refreshed.status == "ready"
    # retrieval works against the provisioned KB
    hits = svc.retrieve(successor.id, "refund approval")
    assert hits and hits[0].source_document_id == "policy.txt"


def test_non_text_doc_marks_partial(tmp_path):
    svc, session = _svc(tmp_path)
    org, role = f"o-{uuid.uuid4().hex[:8]}", f"r-{uuid.uuid4().hex[:8]}"
    svc.create_role(role_id=role, org_id=org, title="X")
    successor = svc.create_successor(role_id=role, org_id=org)
    svc.add_documents(successor.id, [
        ("good.txt", b"hello deploy", "text/plain"),
        ("bad.bin", b"\xff\xfe\x00binary", "application/octet-stream"),
    ])
    job = svc.sync_job(svc.ingest(successor.id).id)
    session.commit()
    assert job.status == "partial"
    assert job.doc_indexed == 1 and job.doc_failed == 1
```

- [ ] **Step 2: Run, confirm fail** `uv run pytest tests/test_ingestion_service.py -v` → ImportError.

- [ ] **Step 3: Create `services/__init__.py`** (`# services package`) and `services/ingestion.py`:
```python
import uuid
from datetime import datetime

from sqlmodel import Session

from continuum_api.knowledge.interface import BlobStore, FoundryKnowledge
from continuum_api.knowledge.types import RetrievedSnippet
from continuum_api.models import (
    Document, IngestionJob, KnowledgeSource, Role, Successor,
)
from continuum_api.repos.capture import (
    DocumentRepo, IngestionJobRepo, KnowledgeSourceRepo, RoleRepo, SuccessorRepo,
)


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


class IngestionService:
    def __init__(self, session: Session, blob: BlobStore, knowledge: FoundryKnowledge) -> None:
        self._s = session
        self._blob = blob
        self._knowledge = knowledge
        self.roles = RoleRepo(session)
        self.successors = SuccessorRepo(session)
        self.sources = KnowledgeSourceRepo(session)
        self.documents = DocumentRepo(session)
        self.jobs = IngestionJobRepo(session)

    # --- creation -------------------------------------------------------
    def create_role(self, *, role_id: str, org_id: str, title: str, description: str = "") -> Role:
        role = self.roles.create(
            Role(id=role_id, org_id=org_id, title=title, description=description)
        )
        self._s.flush()
        return role

    def create_successor(self, *, role_id: str, org_id: str) -> Successor:
        role = self.roles.get(role_id)
        if role is None or role.org_id != org_id:
            raise LookupError("role not found in org")
        kb_name = f"kb-{org_id}-{role_id}"
        self._knowledge.ensure_knowledge_base(kb_name)
        successor = self.successors.create(
            Successor(id=_id("succ"), role_id=role_id, knowledge_base_name=kb_name,
                      status="provisioning")
        )
        container = self._blob.ensure_container(successor.id)
        self.sources.create(
            KnowledgeSource(id=_id("src"), successor_id=successor.id, type="blob",
                            container=container)
        )
        self._s.flush()
        return successor

    # --- documents ------------------------------------------------------
    def add_documents(self, successor_id: str, files: list[tuple[str, bytes, str]]) -> list[Document]:
        source = self.sources.for_successor(successor_id)
        if source is None:
            raise LookupError("successor has no source")
        created: list[Document] = []
        for filename, data, content_type in files:
            blob_path = self._blob.put(source.container, filename, data, content_type)
            created.append(self.documents.create(
                Document(id=_id("doc"), source_id=source.id, filename=filename,
                         content_type=content_type, blob_path=blob_path,
                         size_bytes=len(data), status="uploaded")
            ))
        self._s.flush()
        return created

    # --- ingestion ------------------------------------------------------
    def ingest(self, successor_id: str) -> IngestionJob:
        successor = self.successors.get(successor_id)
        if successor is None:
            raise LookupError("successor not found")
        source = self.sources.for_successor(successor_id)
        docs = self.documents.for_source(source.id)
        for doc in docs:
            doc.status = "indexing"
        self._knowledge.ensure_blob_source(successor.knowledge_base_name, source.container)
        run_ref = self._knowledge.start_indexing(successor.knowledge_base_name)
        job = self.jobs.create(
            IngestionJob(id=_id("job"), successor_id=successor_id, status="running",
                         doc_total=len(docs), started_at=datetime.utcnow(), run_ref=run_ref)
        )
        self._s.flush()
        return job

    def sync_job(self, job_id: str) -> IngestionJob:
        job = self.jobs.get(job_id)
        if job is None:
            raise LookupError("job not found")
        status = self._knowledge.indexing_status(job.run_ref)
        job.doc_indexed = status.indexed
        job.doc_failed = status.failed
        job.error = "; ".join(status.errors)
        successor = self.successors.get(job.successor_id)
        source = self.sources.for_successor(job.successor_id)
        docs = self.documents.for_source(source.id)
        if status.state == "succeeded":
            job.status = "succeeded"
            for doc in docs:
                doc.status = "indexed"
            successor.status = "ready"
        elif status.state == "partial":
            job.status = "partial"
            successor.status = "ready"
        else:
            job.status = "failed"
            successor.status = "failed"
        job.finished_at = datetime.utcnow()
        self._s.flush()
        return job

    # --- read -----------------------------------------------------------
    def get_successor(self, successor_id: str) -> Successor | None:
        return self.successors.get(successor_id)

    def retrieve(self, successor_id: str, query: str, *, top: int = 5) -> list[RetrievedSnippet]:
        successor = self.successors.get(successor_id)
        return self._knowledge.retrieve(successor.knowledge_base_name, query, top=top)
```

- [ ] **Step 4: Run, confirm pass** `uv run pytest tests/test_ingestion_service.py -v` → 2 passed. `uv run ruff check .` → clean.

- [ ] **Step 5: Commit**
```bash
git add apps/api/src/continuum_api/services apps/api/tests/test_ingestion_service.py
git commit -m "feat(capture): IngestionService orchestrates the capture loop (TDD vs fakes)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Backend factory (settings-driven)

**Files:** Create `knowledge/factory.py`, `tests/test_factory.py`

- [ ] **Step 1: Write failing test** `tests/test_factory.py`:
```python
from continuum_api.knowledge.factory import build_blob_store, build_knowledge
from continuum_api.knowledge.fake import FakeFoundryKnowledge
from continuum_api.knowledge.local_blob import LocalBlobStore


def test_defaults_are_local_and_fake():
    blob = build_blob_store()
    assert isinstance(blob, LocalBlobStore)
    assert isinstance(build_knowledge(blob), FakeFoundryKnowledge)
```

- [ ] **Step 2: Run, confirm fail** → ImportError.

- [ ] **Step 3: Create `knowledge/factory.py`**:
```python
from continuum_api.knowledge.interface import BlobStore, FoundryKnowledge
from continuum_api.settings import settings


def build_blob_store() -> BlobStore:
    if settings.blob_backend == "azure":
        from continuum_api.knowledge.azure_blob import AzureBlobStore

        return AzureBlobStore(account_url=settings.azure_storage_account_url)
    from continuum_api.knowledge.local_blob import LocalBlobStore

    return LocalBlobStore(root=settings.blob_local_root)


_fake_knowledge: FoundryKnowledge | None = None


def build_knowledge(blob: BlobStore) -> FoundryKnowledge:
    if settings.knowledge_backend == "foundry":
        from continuum_api.knowledge.foundry import FoundryKnowledgeClient

        return FoundryKnowledgeClient(endpoint=settings.azure_search_endpoint, blob=blob)
    # The fake holds in-memory KB/run state, so it MUST be a process-wide singleton — the
    # API builds a fresh service per request and that state has to survive across requests.
    global _fake_knowledge
    if _fake_knowledge is None:
        from continuum_api.knowledge.fake import FakeFoundryKnowledge

        _fake_knowledge = FakeFoundryKnowledge(blob)
    return _fake_knowledge
```
(The azure imports are lazy so dev/CI never import the Azure SDKs unless configured. The fake is a singleton so its in-memory state persists across requests; `LocalBlobStore` is filesystem-backed so it needs no singleton.)

- [ ] **Step 4: Run, confirm pass** → 1 passed. `uv run ruff check .` → clean.

- [ ] **Step 5: Commit**
```bash
git add apps/api/src/continuum_api/knowledge/factory.py apps/api/tests/test_factory.py
git commit -m "feat(capture): settings-driven backend factory (lazy Azure imports)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Capture API (FastAPI) — TDD with TestClient

**Files:** Create `routes/capture.py`, `tests/test_capture_api.py`; modify `main.py`

Endpoints receive `org_id` via a header the BFF sets (`X-Org-Id`), reuse the `require_service_token` guard, and build the service from the factory + a request-scoped session.

- [ ] **Step 1: Write failing test** `tests/test_capture_api.py`:
```python
import uuid

HEADERS = None  # set in body below


def _headers():
    from continuum_api.settings import settings
    return {"X-Service-Token": settings.api_service_token, "X-Org-Id": "o-api"}


def test_capture_flow_via_api(client):
    role_id = f"r-{uuid.uuid4().hex[:8]}"
    h = _headers()
    # create role (org comes from the X-Org-Id header, not the path)
    r = client.post("/internal/roles", json={"id": role_id, "title": "Ops"}, headers=h)
    assert r.status_code == 201
    # create successor
    r = client.post(f"/internal/roles/{role_id}/successor", headers=h)
    assert r.status_code == 201
    sid = r.json()["id"]
    # upload a document
    r = client.post(
        f"/internal/successors/{sid}/documents",
        files=[("files", ("p.txt", b"Deploys happen on Fridays.", "text/plain"))],
        headers=h,
    )
    assert r.status_code == 201
    # ingest
    r = client.post(f"/internal/successors/{sid}/ingest", headers=h)
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    # poll
    r = client.get(f"/internal/successors/{sid}/ingest/{job_id}", headers=h)
    assert r.json()["status"] == "succeeded"
    # successor ready
    assert client.get(f"/internal/successors/{sid}", headers=h).json()["status"] == "ready"
    # smoke retrieval
    r = client.post(f"/internal/successors/{sid}/query", json={"query": "when do we deploy"}, headers=h)
    hits = r.json()["snippets"]
    assert hits and "Fridays" in hits[0]["content"]


def test_service_token_required(client):
    assert client.get("/internal/successors/whatever").status_code == 401
```

- [ ] **Step 2: Run, confirm fail** `uv run pytest tests/test_capture_api.py -v` → 404/401 (routes absent).

- [ ] **Step 3: Create `routes/capture.py`**:
```python
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session

from continuum_api.db import get_session
from continuum_api.knowledge.factory import build_blob_store, build_knowledge
from continuum_api.routes.internal import require_service_token
from continuum_api.services.ingestion import IngestionService
from continuum_api.settings import settings

router = APIRouter(prefix="/internal", dependencies=[Depends(require_service_token)])


def _service(session: Session) -> IngestionService:
    blob = build_blob_store()
    return IngestionService(session, blob, build_knowledge(blob))


def _org(x_org_id: str | None = Header(default=None)) -> str:
    if not x_org_id:
        raise HTTPException(status_code=400, detail="missing X-Org-Id")
    return x_org_id


class CreateRole(BaseModel):
    id: str
    title: str
    description: str = ""


class QueryBody(BaseModel):
    query: str


@router.post("/roles", status_code=201)
def create_role(body: CreateRole, org: str = Depends(_org),
                session: Session = Depends(get_session)) -> dict:
    # org is derived from the authenticated X-Org-Id header (set by the BFF), not a path
    # param — never trust a client-supplied org id.
    role = _service(session).create_role(
        role_id=body.id, org_id=org, title=body.title, description=body.description
    )
    session.commit()
    return {"id": role.id, "title": role.title}


@router.post("/roles/{role_id}/successor", status_code=201)
def create_successor(role_id: str, org: str = Depends(_org),
                     session: Session = Depends(get_session)) -> dict:
    try:
        successor = _service(session).create_successor(role_id=role_id, org_id=org)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    session.commit()
    return {"id": successor.id, "status": successor.status,
            "knowledge_base_name": successor.knowledge_base_name}


@router.post("/successors/{successor_id}/documents", status_code=201)
async def upload_documents(successor_id: str, files: list[UploadFile],
                           org: str = Depends(_org),
                           session: Session = Depends(get_session)) -> dict:
    payload = [(f.filename or f"file-{uuid.uuid4().hex}", await f.read(),
                f.content_type or "application/octet-stream") for f in files]
    try:
        docs = _service(session).add_documents(successor_id, payload)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    session.commit()
    return {"uploaded": [d.id for d in docs]}


@router.post("/successors/{successor_id}/ingest", status_code=202)
def ingest(successor_id: str, org: str = Depends(_org),
           session: Session = Depends(get_session)) -> dict:
    svc = _service(session)
    try:
        job = svc.ingest(successor_id)
        # local/fake indexing is synchronous; reconcile immediately. (Real Azure:
        # this returns 202 and the client polls the status endpoint until terminal.)
        if settings.knowledge_backend == "fake":
            job = svc.sync_job(job.id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    session.commit()
    return {"job_id": job.id, "status": job.status}


@router.get("/successors/{successor_id}/ingest/{job_id}")
def job_status(successor_id: str, job_id: str, org: str = Depends(_org),
               session: Session = Depends(get_session)) -> dict:
    svc = _service(session)
    job = svc.sync_job(job_id)
    session.commit()
    return {"status": job.status, "doc_total": job.doc_total,
            "doc_indexed": job.doc_indexed, "doc_failed": job.doc_failed}


@router.get("/successors/{successor_id}")
def get_successor(successor_id: str, org: str = Depends(_org),
                  session: Session = Depends(get_session)) -> dict:
    s = _service(session).get_successor(successor_id)
    if s is None:
        raise HTTPException(status_code=404, detail="not found")
    return {"id": s.id, "status": s.status, "knowledge_base_name": s.knowledge_base_name}


@router.post("/successors/{successor_id}/query")
def query(successor_id: str, body: QueryBody, org: str = Depends(_org),
          session: Session = Depends(get_session)) -> dict:
    hits = _service(session).retrieve(successor_id, body.query, top=settings.retrieve_top)
    return {"snippets": [
        {"content": h.content, "title": h.title,
         "source_document_id": h.source_document_id, "score": h.score} for h in hits
    ]}
```

- [ ] **Step 4: Register the router in `main.py`** — add `from continuum_api.routes import capture` and `app.include_router(capture.router)` (keep health + internal + serve()).

- [ ] **Step 5: Run, confirm pass** `uv run pytest tests/test_capture_api.py -v` → 2 passed. Then full suite `uv run pytest -q` → all pass. `uv run ruff check .` → clean.

- [ ] **Step 6: Commit**
```bash
git add apps/api/src/continuum_api/routes/capture.py apps/api/src/continuum_api/main.py apps/api/tests/test_capture_api.py
git commit -m "feat(capture): FastAPI capture endpoints (roles/successor/upload/ingest/query)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: AzureBlobStore (real) — gated integration

**Files:** Create `knowledge/azure_blob.py`, `tests/test_azure_blob_integration.py`

Implements `BlobStore` over `azure-storage-blob` with `DefaultAzureCredential`. Verified only when Azure creds + `RUN_AZURE_INTEGRATION=1` are present; otherwise the test is skipped (CI stays green without Azure).

- [ ] **Step 1: Create `knowledge/azure_blob.py`**:
```python
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient


class AzureBlobStore:
    def __init__(self, account_url: str) -> None:
        self._client = BlobServiceClient(account_url, credential=DefaultAzureCredential())

    def ensure_container(self, successor_id: str) -> str:
        name = f"continuum-{successor_id}"
        container = self._client.get_container_client(name)
        if not container.exists():
            container.create_container()
        return name

    def put(self, container: str, filename: str, data: bytes, content_type: str) -> str:
        from azure.storage.blob import ContentSettings

        self._client.get_blob_client(container, filename).upload_blob(
            data, overwrite=True, content_settings=ContentSettings(content_type=content_type)
        )
        return filename

    def list_paths(self, container: str) -> list[str]:
        return [b.name for b in self._client.get_container_client(container).list_blobs()]

    def read(self, container: str, blob_path: str) -> bytes:
        return self._client.get_blob_client(container, blob_path).download_blob().readall()
```

- [ ] **Step 2: Create gated test** `tests/test_azure_blob_integration.py`:
```python
import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_AZURE_INTEGRATION") != "1",
    reason="set RUN_AZURE_INTEGRATION=1 + AZURE_STORAGE_ACCOUNT_URL + az login to run",
)


def test_azure_blob_roundtrip():
    from continuum_api.knowledge.azure_blob import AzureBlobStore

    store = AzureBlobStore(account_url=os.environ["AZURE_STORAGE_ACCOUNT_URL"])
    container = store.ensure_container(f"it-{uuid.uuid4().hex[:8]}")
    path = store.put(container, "a.txt", b"hello azure", "text/plain")
    assert store.read(container, path) == b"hello azure"
    assert path in store.list_paths(container)
```

- [ ] **Step 3: Verify it SKIPS without creds** `uv run pytest tests/test_azure_blob_integration.py -v` → 1 skipped. `uv run ruff check .` → clean. (If you have Azure: `RUN_AZURE_INTEGRATION=1 AZURE_STORAGE_ACCOUNT_URL=https://<acct>.blob.core.windows.net az login && uv run pytest tests/test_azure_blob_integration.py` → 1 passed.)

- [ ] **Step 4: Commit**
```bash
git add apps/api/src/continuum_api/knowledge/azure_blob.py apps/api/tests/test_azure_blob_integration.py
git commit -m "feat(capture): AzureBlobStore (azure-storage-blob, managed identity) + gated IT

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: FoundryKnowledgeClient (real) — gated integration

**Files:** Create `knowledge/foundry.py`, `tests/test_foundry_integration.py`

Implements `FoundryKnowledge` over Azure AI Search knowledge bases / agentic retrieval (REST `2026-04-01`, `azure-search-documents`), auth via `DefaultAzureCredential`. **The exact SDK call shapes for knowledge-base creation + agentic `retrieve` are new — verify them against the installed `azure-search-documents` version and the Knowledge Bases REST `2026-04-01` reference before running the integration test.** Code is structured so only this file changes if the SDK surface differs.

- [ ] **Step 1: Create `knowledge/foundry.py`**:
```python
from azure.identity import DefaultAzureCredential

from continuum_api.knowledge.interface import BlobStore
from continuum_api.knowledge.types import IndexingStatus, RetrievedSnippet

# api-version 2026-04-01 is the GA Knowledge Bases / agentic retrieval surface.
_API_VERSION = "2026-04-01"


class FoundryKnowledgeClient:
    """Real FoundryKnowledge over Azure AI Search knowledge bases.

    NOTE: the knowledge-base/source/retrieve calls below target the GA
    2026-04-01 surface; confirm method/payload names against the installed
    azure-search-documents version. This is the ONLY file to change if the
    SDK surface differs — the interface (knowledge/interface.py) is stable.
    """

    def __init__(self, endpoint: str, blob: BlobStore) -> None:
        self._endpoint = endpoint
        self._blob = blob
        self._credential = DefaultAzureCredential()

    def ensure_knowledge_base(self, name: str) -> str:
        from azure.search.documents.indexes import KnowledgeBaseClient  # verify import path

        client = KnowledgeBaseClient(self._endpoint, self._credential, api_version=_API_VERSION)
        client.create_or_update_knowledge_base(name)  # idempotent by name
        return name

    def ensure_blob_source(self, kb: str, container: str) -> str:
        from azure.search.documents.indexes import KnowledgeBaseClient

        client = KnowledgeBaseClient(self._endpoint, self._credential, api_version=_API_VERSION)
        client.create_or_update_blob_source(kb, container=container)
        return f"{kb}::{container}"

    def start_indexing(self, kb: str) -> str:
        from azure.search.documents.indexes import KnowledgeBaseClient

        client = KnowledgeBaseClient(self._endpoint, self._credential, api_version=_API_VERSION)
        return client.run_indexer(kb)  # returns a run/operation id

    def indexing_status(self, run: str) -> IndexingStatus:
        from azure.search.documents.indexes import KnowledgeBaseClient

        client = KnowledgeBaseClient(self._endpoint, self._credential, api_version=_API_VERSION)
        s = client.get_indexer_status(run)
        return IndexingStatus(
            state=s.state, indexed=s.items_processed, failed=s.items_failed,
            errors=[e.message for e in (s.errors or [])],
        )

    def retrieve(self, kb: str, query: str, *, top: int = 5) -> list[RetrievedSnippet]:
        from azure.search.documents import KnowledgeRetrievalClient  # verify import path

        client = KnowledgeRetrievalClient(self._endpoint, kb, self._credential,
                                          api_version=_API_VERSION)
        results = client.retrieve(query=query, top=top)
        return [
            RetrievedSnippet(
                content=r["content"], title=r.get("title", r["sourceDocumentId"]),
                source_document_id=r["sourceDocumentId"], score=float(r.get("score", 0.0)),
            )
            for r in results
        ]
```

- [ ] **Step 2: Create gated test** `tests/test_foundry_integration.py`:
```python
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_AZURE_INTEGRATION") != "1",
    reason="set RUN_AZURE_INTEGRATION=1 + AZURE_SEARCH_ENDPOINT + AZURE_STORAGE_ACCOUNT_URL + az login",
)


def test_foundry_index_and_retrieve():
    import uuid

    from continuum_api.knowledge.azure_blob import AzureBlobStore
    from continuum_api.knowledge.foundry import FoundryKnowledgeClient

    blob = AzureBlobStore(account_url=os.environ["AZURE_STORAGE_ACCOUNT_URL"])
    kn = FoundryKnowledgeClient(endpoint=os.environ["AZURE_SEARCH_ENDPOINT"], blob=blob)
    kb = f"kb-it-{uuid.uuid4().hex[:8]}"
    container = blob.ensure_container(kb)
    blob.put(container, "doc.txt", b"Continuum deploys on Fridays.", "text/plain")
    kn.ensure_knowledge_base(kb)
    kn.ensure_blob_source(kb, container)
    run = kn.start_indexing(kb)
    # poll until terminal (omitted: a simple loop with timeout)
    hits = kn.retrieve(kb, "when do we deploy", top=3)
    assert any("Friday" in h.content for h in hits)
```

- [ ] **Step 3: Verify it SKIPS without creds** `uv run pytest tests/test_foundry_integration.py -v` → 1 skipped. `uv run ruff check .` → clean.

- [ ] **Step 4: Commit**
```bash
git add apps/api/src/continuum_api/knowledge/foundry.py apps/api/tests/test_foundry_integration.py
git commit -m "feat(capture): FoundryKnowledgeClient (azure-search-documents) + gated IT

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: BFF capture routes (web)

**Files:** Create `apps/web/src/lib/capture-api.ts`, `apps/web/src/app/api/bff/capture/[...path]/route.ts`

A thin authenticated proxy: validate the Better Auth session, attach `X-Service-Token` + `X-Org-Id` (the user's active org), forward to FastAPI `/internal/...`. Keep it generic over the capture sub-paths.

- [ ] **Step 1: Create `apps/web/src/lib/capture-api.ts`**:
```typescript
const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";
const SERVICE_TOKEN = process.env.SERVICE_TOKEN ?? "dev-shared-service-token";

export async function forwardToApi(
  path: string,
  init: RequestInit,
  orgId: string,
): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("X-Service-Token", SERVICE_TOKEN);
  headers.set("X-Org-Id", orgId);
  return fetch(`${API_BASE_URL}/internal/${path}`, { ...init, headers, cache: "no-store" });
}
```

- [ ] **Step 2: Create `apps/web/src/app/api/bff/capture/[...path]/route.ts`**:
```typescript
import { NextRequest, NextResponse } from "next/server";
import { headers } from "next/headers";
import { auth } from "@/lib/auth";
import { forwardToApi } from "@/lib/capture-api";

async function resolveOrg(): Promise<{ userId: string; orgId: string } | null> {
  const session = await auth.api.getSession({ headers: await headers() });
  const orgId = session?.session?.activeOrganizationId;
  if (!session?.user || !orgId) return null;
  return { userId: session.user.id, orgId };
}

async function handle(req: NextRequest, path: string[]): Promise<Response> {
  const ctx = await resolveOrg();
  if (!ctx) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const init: RequestInit = { method: req.method };
  if (req.method !== "GET") init.body = await req.arrayBuffer();
  const contentType = req.headers.get("content-type");
  if (contentType) init.headers = { "content-type": contentType };
  const upstream = await forwardToApi(path.join("/"), init, ctx.orgId);
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
}

export async function GET(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return handle(req, (await params).path);
}
export async function POST(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return handle(req, (await params).path);
}
```

- [ ] **Step 3: Verify build + lint** `pnpm --filter web typecheck` → exit 0; `pnpm check` → clean; `pnpm --filter web build` → green.

- [ ] **Step 4: Commit**
```bash
git add apps/web/src/lib/capture-api.ts apps/web/src/app/api/bff/capture
git commit -m "feat(web): BFF proxy for capture endpoints (session -> X-Service-Token/X-Org-Id)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 14: Minimal admin page (observe the loop)

**Files:** Create `apps/web/src/app/admin/page.tsx`

A single client page: enter a Role title → create role + successor → upload a `.txt`/`.md` file → ingest → poll status until `succeeded`/`ready` → run a test query and show snippets. Satisfies acceptance #5 ("observable from the admin UI").

- [ ] **Step 1: Create `apps/web/src/app/admin/page.tsx`**:
```tsx
"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

type Snippet = { content: string; source_document_id: string; score: number };

async function bff(path: string, init?: RequestInit) {
  const res = await fetch(`/api/bff/capture/${path}`, init);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

export default function Admin() {
  const [title, setTitle] = useState("Support Lead");
  const [file, setFile] = useState<File | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const [snippets, setSnippets] = useState<Snippet[]>([]);
  const say = (m: string) => setLog((l) => [...l, m]);

  async function run() {
    setLog([]);
    setSnippets([]);
    const roleId = `r-${crypto.randomUUID().slice(0, 8)}`;
    say(`creating role ${roleId}…`);
    await bff("roles", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: roleId, title }),
    });
    const succ = await bff(`roles/${roleId}/successor`, { method: "POST" });
    say(`successor ${succ.id} (${succ.status})`);
    if (file) {
      const fd = new FormData();
      fd.append("files", file);
      await bff(`successors/${succ.id}/documents`, { method: "POST", body: fd });
      say(`uploaded ${file.name}`);
    }
    const job = await bff(`successors/${succ.id}/ingest`, { method: "POST" });
    say(`ingest job ${job.job_id}: ${job.status}`);
    const s = await bff(`successors/${succ.id}`);
    say(`successor status: ${s.status}`);
    const q = await bff(`successors/${succ.id}/query`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query: "what should I know" }),
    });
    setSnippets(q.snippets);
  }

  return (
    <main className="mx-auto max-w-2xl space-y-4 p-8">
      <h1 className="text-2xl font-semibold">Continuum — Capture (admin)</h1>
      <Card className="space-y-3 p-4">
        <input
          className="w-full rounded-md border border-border bg-background px-3 py-2"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <input type="file" accept=".txt,.md" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <Button onClick={() => void run()}>Build successor from doc</Button>
      </Card>
      {log.length > 0 && (
        <Card className="p-4">
          <pre className="whitespace-pre-wrap text-sm">{log.join("\n")}</pre>
        </Card>
      )}
      {snippets.length > 0 && (
        <Card className="space-y-2 p-4">
          <p className="font-medium">Retrieved knowledge</p>
          {snippets.map((s, i) => (
            <div key={i} className="rounded-md bg-muted/40 p-2 text-sm">
              <span className="text-muted-foreground">{s.source_document_id}</span>
              <p>{s.content}</p>
            </div>
          ))}
        </Card>
      )}
    </main>
  );
}
```

- [ ] **Step 2: Verify** `pnpm --filter web typecheck` → exit 0; `pnpm check` → clean; `pnpm --filter web build` → green.

- [ ] **Step 3: Manual smoke (optional, services up):** start Postgres + api + web; sign in (or temporarily relax the BFF org check for the demo); open `/admin`, upload a `.txt`, click build → log shows `ready` and snippets render. (Auth note: the admin page needs a session with an active org; for a pure-local demo without Entra, you can hardcode an org in the BFF or seed a session — track this with the env follow-up in `docs/context/STATE.md`.)

- [ ] **Step 4: Commit**
```bash
git add apps/web/src/app/admin/page.tsx
git commit -m "feat(web): minimal capture admin page (build successor from a doc, show retrieval)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification (run after all tasks)

```bash
docker compose up -d
(cd apps/api && uv run alembic upgrade head && uv run pytest -q)   # all pass; Azure ITs skipped
pnpm turbo run lint typecheck test build                          # whole repo green
```

## Definition of Done

- Create Role + Successor → a knowledge base is provisioned (idempotent); upload docs → ingest → job `succeeded`/`partial` with per-doc errors surfaced → `Successor.status=ready`.
- `POST /internal/successors/{id}/query` returns ≥1 grounded snippet with a `source_document_id` for an answerable question; empty for an unanswerable one.
- The whole loop runs locally with `local`/`fake` backends (no Azure); flips to real Azure by setting `blob_backend=azure`, `knowledge_backend=foundry` + the Azure endpoints. Real Azure verified by the gated `@integration` tests.
- The admin page drives + observes the loop end-to-end.
- Better Auth tables remain intact; capture tables are Alembic-owned and in `_MANAGED_TABLES`.

## Notes for the implementer

- **Never `alembic revision --autogenerate`** — hand-write migrations; new tables go in `_MANAGED_TABLES` (`apps/api/AGENTS.md`).
- The **real Foundry/Search SDK call shapes (Task 12) are new** — verify against the installed `azure-search-documents` + the Knowledge Bases REST `2026-04-01` docs before running the integration test. The `FoundryKnowledge` interface is the stable contract; only `foundry.py` changes if the SDK differs.
- `ingest` reconciles synchronously for the `fake` backend (returns terminal status immediately). For real Azure, indexing is async — the endpoint returns 202 and the admin page polls `…/ingest/{job_id}` until terminal (`sync_job` is idempotent thanks to the dedicated `run_ref` column).
- The `fake` knowledge backend is a process-wide singleton (`knowledge/factory.py`) because it holds in-memory KB/run state that must survive across requests; the real Foundry client is stateless/remote and needs no singleton.
- Spec 2 (mentor) consumes `FoundryKnowledge.retrieve` + the `Successor` — keep the interface in `knowledge/interface.py` stable.
