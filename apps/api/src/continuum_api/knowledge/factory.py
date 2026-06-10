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


def reset_fake_knowledge() -> None:
    """Reset the fake singleton between tests for isolation. Not for production use."""
    global _fake_knowledge
    _fake_knowledge = None
