import pytest

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


def test_reindex_replaces_state_not_doubles(tmp_path):
    kn, kb, _ = _setup(tmp_path)
    run2 = kn.start_indexing(kb)
    assert kn.indexing_status(run2).indexed == 1  # not 2
    hits = kn.retrieve(kb, "refund approval", top=5)
    assert len(hits) <= 2  # chunks replaced, not appended


def test_run_status_snapshots_are_independent(tmp_path):
    kn, kb, run1 = _setup(tmp_path)
    run2 = kn.start_indexing(kb)
    assert run1 != run2
    assert kn.indexing_status(run1).indexed == 1  # first run's snapshot intact
    assert kn.indexing_status(run2).indexed == 1


def test_start_indexing_without_source_raises(tmp_path):
    blob = LocalBlobStore(root=str(tmp_path))
    kn = FakeFoundryKnowledge(blob)
    kn.ensure_knowledge_base("kb-x")
    with pytest.raises(RuntimeError):
        kn.start_indexing("kb-x")
