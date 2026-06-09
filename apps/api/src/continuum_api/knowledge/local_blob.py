from pathlib import Path


class LocalBlobStore:
    def __init__(self, root: str) -> None:
        self._root = Path(root)

    def ensure_container(self, successor_id: str) -> str:
        container = f"continuum-{successor_id}"
        (self._root / container).mkdir(parents=True, exist_ok=True)
        return container

    def put(self, container: str, filename: str, data: bytes, content_type: str) -> str:
        # Flatten to a bare filename: blobs are flat (matches Azure), and this
        # neutralizes path traversal (e.g. "../../evil") from uploaded filenames.
        safe_name = Path(filename).name
        target = self._root / container / safe_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return safe_name

    def list_paths(self, container: str) -> list[str]:
        base = self._root / container
        if not base.exists():
            return []
        return sorted(p.name for p in base.iterdir() if p.is_file())

    def read(self, container: str, blob_path: str) -> bytes:
        return (self._root / container / blob_path).read_bytes()
