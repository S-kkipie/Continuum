from pathlib import Path

from continuum_api.knowledge.local_blob import LocalBlobStore


def test_put_read_list_roundtrip(tmp_path: Path):
    store = LocalBlobStore(root=str(tmp_path))
    container = store.ensure_container("succ-1")
    path = store.put(container, "a.txt", b"hello world", "text/plain")
    assert store.read(container, path) == b"hello world"
    assert path in store.list_paths(container)


def test_containers_are_isolated(tmp_path: Path):
    store = LocalBlobStore(root=str(tmp_path))
    c1 = store.ensure_container("s1")
    c2 = store.ensure_container("s2")
    store.put(c1, "x.txt", b"one", "text/plain")
    assert store.list_paths(c2) == []


def test_put_strips_path_traversal(tmp_path: Path):
    store = LocalBlobStore(root=str(tmp_path))
    container = store.ensure_container("s1")
    returned = store.put(container, "../../evil.txt", b"x", "text/plain")
    assert returned == "evil.txt"
    # nothing was written outside the container root
    assert store.list_paths(container) == ["evil.txt"]
    assert not (tmp_path / "evil.txt").exists()
