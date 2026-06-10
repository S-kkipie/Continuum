"""Gated integration test for FoundryKnowledgeClient.

Requires real Azure credentials and resources — SKIPPED in CI unless
``RUN_AZURE_INTEGRATION=1`` is set.

To run locally:
  export RUN_AZURE_INTEGRATION=1
  export AZURE_SEARCH_ENDPOINT=https://<your-search-service>.search.windows.net
  export AZURE_STORAGE_ACCOUNT_URL=https://<your-storage-account>.blob.core.windows.net
  az login  (or set AZURE_CLIENT_ID / AZURE_CLIENT_SECRET / AZURE_TENANT_ID for service-principal)
  cd apps/api && uv run pytest tests/test_foundry_integration.py -v

NOTE: the azure-search-documents==12.0.0 SDK shape has been verified and documented in
knowledge/foundry.py.  The SDK call shapes used here (KnowledgeBaseRetrievalClient,
SearchIndexClient.create_or_update_knowledge_base, get_knowledge_source_status, etc.) match
the installed 12.0.0 surface.  Verify that the Azure service tier supports the 2026-04-01
api-version before running.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_AZURE_INTEGRATION") != "1",
    reason=(
        "set RUN_AZURE_INTEGRATION=1 + AZURE_SEARCH_ENDPOINT + AZURE_STORAGE_ACCOUNT_URL + az login"
    ),
)


def test_foundry_index_and_retrieve():
    import time
    import uuid

    from continuum_api.knowledge.azure_blob import AzureBlobStore
    from continuum_api.knowledge.foundry import FoundryKnowledgeClient

    # NOTE: no teardown — the kb + container are left in Azure after a live run; delete manually.
    blob = AzureBlobStore(account_url=os.environ["AZURE_STORAGE_ACCOUNT_URL"])
    kn = FoundryKnowledgeClient(endpoint=os.environ["AZURE_SEARCH_ENDPOINT"], blob=blob)

    kb = f"kb-it-{uuid.uuid4().hex[:8]}"
    container = blob.ensure_container(kb)
    blob.put(container, "doc.txt", b"Continuum deploys on Fridays.", "text/plain")

    kn.ensure_knowledge_base(kb)
    kn.ensure_blob_source(kb, container)
    run = kn.start_indexing(kb)

    # TODO: terminal synchronization_status string is unconfirmed — update the poll
    # exit condition once the first real IT run reveals what Azure returns for "done".
    # Poll until terminal state (up to 120 s)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        status = kn.indexing_status(run)
        if status.state not in ("running", "creating", "active"):
            break
        time.sleep(5)

    hits = kn.retrieve(kb, "when do we deploy", top=3)
    assert any("Friday" in h.content for h in hits), f"No Friday hit in: {hits}"
