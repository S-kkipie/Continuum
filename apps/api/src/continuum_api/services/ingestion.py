import uuid
from datetime import datetime

from sqlmodel import Session

from continuum_api.knowledge.interface import BlobStore, FoundryKnowledge
from continuum_api.knowledge.types import RetrievedSnippet
from continuum_api.models import (
    Document,
    IngestionJob,
    KnowledgeSource,
    Role,
    Successor,
)
from continuum_api.repos.capture import (
    DocumentRepo,
    IngestionJobRepo,
    KnowledgeSourceRepo,
    RoleRepo,
    SuccessorRepo,
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
            Successor(
                id=_id("succ"),
                role_id=role_id,
                knowledge_base_name=kb_name,
                status="provisioning",
            )
        )
        container = self._blob.ensure_container(successor.id)
        self.sources.create(
            KnowledgeSource(
                id=_id("src"),
                successor_id=successor.id,
                type="blob",
                container=container,
            )
        )
        self._s.flush()
        return successor

    # --- documents ------------------------------------------------------
    def add_documents(
        self, successor_id: str, files: list[tuple[str, bytes, str]]
    ) -> list[Document]:
        source = self.sources.for_successor(successor_id)
        if source is None:
            raise LookupError("successor has no source")
        created: list[Document] = []
        for filename, data, content_type in files:
            blob_path = self._blob.put(source.container, filename, data, content_type)
            created.append(
                self.documents.create(
                    Document(
                        id=_id("doc"),
                        source_id=source.id,
                        filename=filename,
                        content_type=content_type,
                        blob_path=blob_path,
                        size_bytes=len(data),
                        status="uploaded",
                    )
                )
            )
        self._s.flush()
        return created

    # --- ingestion ------------------------------------------------------
    def ingest(self, successor_id: str) -> IngestionJob:
        successor = self.successors.get(successor_id)
        if successor is None:
            raise LookupError("successor not found")
        source = self.sources.for_successor(successor_id)
        if source is None:
            raise LookupError("successor has no knowledge source")
        docs = self.documents.for_source(source.id)
        for doc in docs:
            doc.status = "indexing"
        self._knowledge.ensure_blob_source(successor.knowledge_base_name, source.container)
        run_ref = self._knowledge.start_indexing(successor.knowledge_base_name)
        job = self.jobs.create(
            IngestionJob(
                id=_id("job"),
                successor_id=successor_id,
                status="running",
                doc_total=len(docs),
                started_at=datetime.utcnow(),
                run_ref=run_ref,
            )
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
        if successor is None:
            raise LookupError("successor not found for job")
        source = self.sources.for_successor(job.successor_id)
        if source is None:
            raise LookupError("successor has no knowledge source")
        docs = self.documents.for_source(source.id)
        if status.state == "succeeded":
            job.status = "succeeded"
            for doc in docs:
                doc.status = "indexed"
            successor.status = "ready"
        elif status.state == "partial":
            job.status = "partial"
            # Reconcile per-doc from the error lines. The indexing layer formats each
            # error as "<path>: <reason>" where <path> is the document's blob_path.
            # Docs whose path appears in an error are marked failed (with that message);
            # the rest are considered indexed. (For backends whose error strings don't
            # carry the path, no doc matches and all are marked indexed — best effort.)
            failed_by_path: dict[str, str] = {}
            for err in status.errors:
                path = err.split(":", 1)[0].strip()
                failed_by_path.setdefault(path, err)
            for doc in docs:
                if doc.blob_path in failed_by_path:
                    doc.status = "failed"
                    doc.error = failed_by_path[doc.blob_path]
                else:
                    doc.status = "indexed"
            successor.status = "ready"
        else:
            job.status = "failed"
            for doc in docs:
                doc.status = "failed"
            successor.status = "failed"
        job.finished_at = datetime.utcnow()
        self._s.flush()
        return job

    # --- read -----------------------------------------------------------
    def successor_in_org(self, successor_id: str, org_id: str) -> bool:
        successor = self.successors.get(successor_id)
        if successor is None:
            return False
        role = self.roles.get(successor.role_id)
        return role is not None and role.org_id == org_id

    def get_successor(self, successor_id: str) -> Successor | None:
        return self.successors.get(successor_id)

    def retrieve(
        self, successor_id: str, query: str, *, top: int = 5
    ) -> list[RetrievedSnippet]:
        successor = self.successors.get(successor_id)
        if successor is None:
            raise LookupError("successor not found")
        return self._knowledge.retrieve(successor.knowledge_base_name, query, top=top)
