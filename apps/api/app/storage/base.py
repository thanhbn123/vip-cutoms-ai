"""Document storage abstraction. DB rows hold opaque keys only — never public URLs."""

from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings


class Storage(Protocol):
    name: str

    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...


class LocalFileStorage:
    """Private local directory (dev / single-host staging). S3/NAS adapters implement the same protocol."""

    name = "local"

    def __init__(self, base_dir: str):
        self.base = Path(base_dir).resolve()
        self.base.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.base / key).resolve()
        if self.base not in p.parents:
            raise ValueError("invalid storage key")
        return p

    def put(self, key: str, data: bytes) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, p)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@lru_cache
def get_storage() -> Storage:
    s = get_settings()
    if s.object_storage_provider == "local":
        return LocalFileStorage(os.environ.get("LOCAL_STORAGE_DIR", s.local_storage_dir))
    raise RuntimeError(f"storage provider '{s.object_storage_provider}' not available in this build")
