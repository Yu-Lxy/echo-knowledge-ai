"""LocalStorage 单元测试（不依赖数据库）。"""

import pytest

from app.storage.local import LocalStorage, StorageError, sha256_stream


@pytest.fixture
def store(tmp_path):
    return LocalStorage(root=str(tmp_path / "storage"))


def _blocks(data: bytes, size: int = 4) -> "list[bytes]":
    return [data[i : i + size] for i in range(0, len(data), size)]


SHA_OF_ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"  # sha256("abc")


def test_put_and_open_roundtrip(store):
    key = SHA_OF_ABC
    size = store.put(key, iter(_blocks(b"abc")))
    assert size == 3
    assert store.exists(key)
    data = b"".join(store.open(key))
    assert data == b"abc"
    # 内容寻址布局：{sha[:2]}/{sha}
    assert (store.root / key[:2] / key).is_file()


def test_open_missing_raises(store):
    with pytest.raises(StorageError):
        list(store.open(SHA_OF_ABC))


def test_delete_idempotent(store):
    store.put(SHA_OF_ABC, iter(_blocks(b"abc")))
    store.delete(SHA_OF_ABC)
    store.delete(SHA_OF_ABC)  # 不存在也静默成功（清理任务可安全重放）
    assert not store.exists(SHA_OF_ABC)


def test_temp_key_flow(store):
    tmp_key = store.temp_key()
    assert tmp_key.startswith("tmp:")
    store.put(tmp_key, iter(_blocks(b"draft")))
    assert b"".join(store.open(tmp_key)) == b"draft"
    store.delete(tmp_key)
    assert not store.exists(tmp_key)


def test_invalid_content_key_rejected(store):
    with pytest.raises(StorageError):
        store.put("not-a-sha", iter(_blocks(b"x")))
    # 探测类操作对非法键返回 False 而非抛错（不中断调用方流程）
    assert store.exists("not-a-sha") is False


def test_path_traversal_immune(store):
    for evil in ("../../etc/passwd", "..\\..\\x", "aa/../..", "/etc/passwd", "a/b"):
        with pytest.raises(StorageError):
            store.put(evil, iter(_blocks(b"x")))


def test_put_overwrite_same_key(store):
    store.put(SHA_OF_ABC, iter(_blocks(b"abc")))
    store.put(SHA_OF_ABC, iter(_blocks(b"abc")))  # 同内容幂等覆盖
    assert b"".join(store.open(SHA_OF_ABC)) == b"abc"


def test_sha256_stream():
    digest, size = sha256_stream(iter(_blocks(b"abc", size=1)))
    assert digest == SHA_OF_ABC
    assert size == 3

    big = b"abc" * 100
    d2, s2 = sha256_stream(iter(_blocks(big, size=7)))
    import hashlib

    assert d2 == hashlib.sha256(big).hexdigest()
    assert s2 == 300
