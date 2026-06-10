from pathlib import Path

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

        # Flatten to bare filename for parity with LocalBlobStore: blobs are logically flat
        # per-container, and this neutralises path-traversal (e.g. "../../evil") in filenames.
        filename = Path(filename).name
        self._client.get_blob_client(container, filename).upload_blob(
            data, overwrite=True, content_settings=ContentSettings(content_type=content_type)
        )
        return filename

    def list_paths(self, container: str) -> list[str]:
        return [b.name for b in self._client.get_container_client(container).list_blobs()]

    def read(self, container: str, blob_path: str) -> bytes:
        return self._client.get_blob_client(container, blob_path).download_blob().readall()
