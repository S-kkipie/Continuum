import uuid

import pytest
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
    svc.add_documents(
        successor.id, [("policy.txt", b"Refunds need manager approval.", "text/plain")]
    )
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

    # per-doc reconciliation: good.txt indexed, bad.bin failed with an error
    source = svc.sources.for_successor(successor.id)
    docs = {d.filename: d for d in svc.documents.for_source(source.id)}
    assert docs["good.txt"].status == "indexed"
    assert docs["bad.bin"].status == "failed"
    assert docs["bad.bin"].error  # non-empty error message


def test_retrieve_unknown_successor_raises(tmp_path):
    svc, _ = _svc(tmp_path)
    with pytest.raises(LookupError):
        svc.retrieve("succ-does-not-exist", "anything")
