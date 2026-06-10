import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_AZURE_INTEGRATION") != "1",
    reason="set RUN_AZURE_INTEGRATION=1 + AZURE_STORAGE_ACCOUNT_URL + az login to run",
)


def test_azure_blob_roundtrip():
    from continuum_api.knowledge.azure_blob import AzureBlobStore

    account_url = os.environ.get("AZURE_STORAGE_ACCOUNT_URL")
    if not account_url:
        pytest.skip("AZURE_STORAGE_ACCOUNT_URL not set")

    store = AzureBlobStore(account_url=account_url)
    container = store.ensure_container(f"it-{uuid.uuid4().hex[:8]}")
    try:
        path = store.put(container, "a.txt", b"hello azure", "text/plain")
        assert store.read(container, path) == b"hello azure"
        assert path in store.list_paths(container)
    finally:
        store._client.get_container_client(container).delete_container()
