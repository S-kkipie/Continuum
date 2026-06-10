from continuum_api.knowledge.factory import build_blob_store, build_knowledge
from continuum_api.knowledge.fake import FakeFoundryKnowledge
from continuum_api.knowledge.local_blob import LocalBlobStore


def test_defaults_are_local_and_fake():
    blob = build_blob_store()
    assert isinstance(blob, LocalBlobStore)
    assert isinstance(build_knowledge(blob), FakeFoundryKnowledge)


def test_build_knowledge_returns_singleton():
    blob = build_blob_store()
    assert build_knowledge(blob) is build_knowledge(blob)
