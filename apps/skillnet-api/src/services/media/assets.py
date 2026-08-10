"""On-disk asset store for generated media, deduped by content hash (spine item #3).

Mirrors the existing TTS disk cache (``src/services/tts_service.py`` ``TTSCache``): bytes
are written under a directory, named by a SHA-256 of their content, with an atomic
temp-file-then-rename so a concurrent reader never sees a half-written file. Because the
name **is** the content hash, storing the same bytes twice is a no-op — the dedup the
roadmap asks for (§2 "Asset store: dedup by content_hash") falls out of the naming scheme
rather than needing a table lookup.

Unlike the TTS cache (always mp3) this store holds several media types, so the extension
is part of the file name: ``{hash}.{ext}``. The hash alone still identifies the content;
the extension only tells the OS and the HTTP layer what it is.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from src.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


def content_hash(data: bytes) -> str:
    """The SHA-256 hex digest used as both the dedup key and the file stem."""
    return hashlib.sha256(data).hexdigest()


def _normalize_ext(ext: str) -> str:
    """``.PNG`` / ``png`` -> ``png``. Empty means an extensionless blob."""
    return ext.lstrip(".").lower()


@dataclass(frozen=True)
class StoredAsset:
    """The result of storing bytes: the dedup key and where it landed."""

    content_hash: str
    path: str
    ext: str
    size: int


class AssetStore:
    """Content-addressed file store for generated media bytes."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.base_dir = Path(base_dir or settings.MEDIA_ASSETS_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, digest: str, ext: str) -> Path:
        ext = _normalize_ext(ext)
        name = f"{digest}.{ext}" if ext else digest
        return self.base_dir / name

    def path_for(self, digest: str, ext: str) -> Path:
        """Where bytes with this hash/extension would live. Does not touch the disk."""
        return self._path(digest, ext)

    def exists(self, digest: str, ext: str) -> bool:
        return self._path(digest, ext).exists()

    def store(self, data: bytes, ext: str) -> StoredAsset:
        """Write ``data`` (dedup by content). Returns the hash, path, ext and size.

        If a file with the same content hash already exists, nothing is written and the
        existing path is returned — that is the dedup. The write is atomic (temp file in
        the same directory, then ``os.replace``), so a reader either sees the whole file
        or nothing.
        """
        digest = content_hash(data)
        ext = _normalize_ext(ext)
        path = self._path(digest, ext)
        if path.exists():
            logger.debug("Asset store dedup hit: %s", path.name)
            return StoredAsset(
                content_hash=digest, path=str(path), ext=ext, size=path.stat().st_size
            )

        fd, tmp_path = tempfile.mkstemp(dir=str(self.base_dir))
        closed = False
        try:
            os.write(fd, data)
            os.close(fd)
            closed = True
            os.replace(tmp_path, str(path))
        except BaseException:
            if not closed:
                os.close(fd)
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        logger.debug("Asset store write: %s (%d bytes)", path.name, len(data))
        return StoredAsset(
            content_hash=digest, path=str(path), ext=ext, size=len(data)
        )

    def read(self, path: str | Path) -> bytes:
        """Read stored bytes back. Raises ``FileNotFoundError`` if the asset is gone."""
        return Path(path).read_bytes()


__all__ = ["AssetStore", "StoredAsset", "content_hash"]
