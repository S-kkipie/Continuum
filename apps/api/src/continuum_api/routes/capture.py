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
def create_role(
    body: CreateRole,
    org: str = Depends(_org),
    session: Session = Depends(get_session),
) -> dict:
    # org is derived from the authenticated X-Org-Id header (set by the BFF), not a path
    # param — never trust a client-supplied org id.
    role = _service(session).create_role(
        role_id=body.id, org_id=org, title=body.title, description=body.description
    )
    session.commit()
    return {"id": role.id, "title": role.title}


@router.post("/roles/{role_id}/successor", status_code=201)
def create_successor(
    role_id: str,
    org: str = Depends(_org),
    session: Session = Depends(get_session),
) -> dict:
    try:
        successor = _service(session).create_successor(role_id=role_id, org_id=org)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    session.commit()
    return {
        "id": successor.id,
        "status": successor.status,
        "knowledge_base_name": successor.knowledge_base_name,
    }


@router.post("/successors/{successor_id}/documents", status_code=201)
async def upload_documents(
    successor_id: str,
    files: list[UploadFile],
    org: str = Depends(_org),
    session: Session = Depends(get_session),
) -> dict:
    payload = [
        (
            f.filename or f"file-{uuid.uuid4().hex}",
            await f.read(),
            f.content_type or "application/octet-stream",
        )
        for f in files
    ]
    try:
        docs = _service(session).add_documents(successor_id, payload)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    session.commit()
    return {"uploaded": [d.id for d in docs]}


@router.post("/successors/{successor_id}/ingest", status_code=202)
def ingest(
    successor_id: str,
    org: str = Depends(_org),
    session: Session = Depends(get_session),
) -> dict:
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
def job_status(
    successor_id: str,
    job_id: str,
    org: str = Depends(_org),
    session: Session = Depends(get_session),
) -> dict:
    # TODO(v2): enforce org ownership on this read path; today the BFF is the org boundary.
    svc = _service(session)
    try:
        job = svc.sync_job(job_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    session.commit()
    return {
        "status": job.status,
        "doc_total": job.doc_total,
        "doc_indexed": job.doc_indexed,
        "doc_failed": job.doc_failed,
    }


@router.get("/successors/{successor_id}")
def get_successor(
    successor_id: str,
    org: str = Depends(_org),
    session: Session = Depends(get_session),
) -> dict:
    # TODO(v2): enforce org ownership on this read path; today the BFF is the org boundary.
    s = _service(session).get_successor(successor_id)
    if s is None:
        raise HTTPException(status_code=404, detail="not found")
    return {"id": s.id, "status": s.status, "knowledge_base_name": s.knowledge_base_name}


@router.post("/successors/{successor_id}/query")
def query(
    successor_id: str,
    body: QueryBody,
    org: str = Depends(_org),
    session: Session = Depends(get_session),
) -> dict:
    # TODO(v2): enforce org ownership on this read path; today the BFF is the org boundary.
    try:
        hits = _service(session).retrieve(successor_id, body.query, top=settings.retrieve_top)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {
        "snippets": [
            {
                "content": h.content,
                "title": h.title,
                "source_document_id": h.source_document_id,
                "score": h.score,
            }
            for h in hits
        ]
    }
