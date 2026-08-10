"""Unit tests for the content-hash asset store (pure disk I/O, no DB/network)."""

from pathlib import Path

from src.services.media.assets import AssetStore, content_hash


def test_store_roundtrip(tmp_path: Path) -> None:
    store = AssetStore(tmp_path)
    data = b"\x89PNG fake bytes"

    stored = store.store(data, "png")

    assert stored.content_hash == content_hash(data)
    assert stored.ext == "png"
    assert stored.size == len(data)
    assert Path(stored.path).name == f"{stored.content_hash}.png"
    assert store.read(stored.path) == data


def test_store_dedupes_identical_content(tmp_path: Path) -> None:
    store = AssetStore(tmp_path)
    data = b"same bytes"

    first = store.store(data, "mp3")
    # Mutating mtime lets us prove the second store did not rewrite the file.
    marker = Path(first.path).stat().st_mtime_ns

    second = store.store(data, "mp3")

    assert second.path == first.path
    assert second.content_hash == first.content_hash
    assert Path(second.path).stat().st_mtime_ns == marker
    # Exactly one file on disk for the deduped content.
    assert len(list(tmp_path.iterdir())) == 1


def test_different_content_yields_different_paths(tmp_path: Path) -> None:
    store = AssetStore(tmp_path)

    a = store.store(b"alpha", "png")
    b = store.store(b"beta", "png")

    assert a.content_hash != b.content_hash
    assert a.path != b.path
    assert len(list(tmp_path.iterdir())) == 2


def test_extension_is_normalized(tmp_path: Path) -> None:
    store = AssetStore(tmp_path)

    stored = store.store(b"x", ".PNG")

    assert stored.ext == "png"
    assert stored.path.endswith(".png")


def test_exists_and_path_for_do_not_write(tmp_path: Path) -> None:
    store = AssetStore(tmp_path)
    digest = content_hash(b"never stored")

    assert store.exists(digest, "mp4") is False
    # path_for is a pure computation; it must not create the file.
    _ = store.path_for(digest, "mp4")
    assert store.exists(digest, "mp4") is False
    assert list(tmp_path.iterdir()) == []
