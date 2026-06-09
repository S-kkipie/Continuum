from sqlmodel import Session, select

from continuum_api.models import (
    Document,
    IngestionJob,
    KnowledgeSource,
    Role,
    Successor,
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
        return list(
            self._s.exec(
                select(Role).where(Role.org_id == org_id).order_by(Role.created_at)
            )
        )


class SuccessorRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, successor: Successor) -> Successor:
        self._s.add(successor)
        return successor

    def get(self, successor_id: str) -> Successor | None:
        return self._s.get(Successor, successor_id)

    def by_role(self, role_id: str) -> Successor | None:
        return self._s.exec(
            select(Successor).where(Successor.role_id == role_id)
        ).one_or_none()


class KnowledgeSourceRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, source: KnowledgeSource) -> KnowledgeSource:
        self._s.add(source)
        return source

    def for_successor(self, successor_id: str) -> KnowledgeSource | None:
        return self._s.exec(
            select(KnowledgeSource)
            .where(KnowledgeSource.successor_id == successor_id)
            .order_by(KnowledgeSource.created_at)
        ).first()


class DocumentRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, doc: Document) -> Document:
        self._s.add(doc)
        return doc

    def for_source(self, source_id: str) -> list[Document]:
        return list(
            self._s.exec(
                select(Document)
                .where(Document.source_id == source_id)
                .order_by(Document.created_at)
            )
        )


class IngestionJobRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, job: IngestionJob) -> IngestionJob:
        self._s.add(job)
        return job

    def get(self, job_id: str) -> IngestionJob | None:
        return self._s.get(IngestionJob, job_id)
