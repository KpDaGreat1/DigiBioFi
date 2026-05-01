from abc import ABC, abstractmethod
from pathlib import Path
import shutil
import os
from typing import BinaryIO

from app.core.config import settings

class StorageInterface(ABC):
    @abstractmethod
    def save(self, file: BinaryIO, path: str) -> str:
        """Save a file-like object to storage and return the relative path."""
        pass

    @abstractmethod
    def delete(self, path: str) -> bool:
        """Delete a file from storage."""
        pass

    @abstractmethod
    def get_url(self, path: str) -> str:
        """Get the public URL for a given path."""
        pass

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Check if a file exists in storage."""
        pass

class LocalStorage(StorageInterface):
    def __init__(self, base_dir: str | None = None, url_prefix: str = "/uploads"):
        self._base_dir = base_dir
        self.url_prefix = url_prefix.rstrip("/")

    @property
    def base_dir(self) -> Path:
        base_dir = Path(self._base_dir or settings.upload_dir)
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir

    def _normalize_relative_path(self, path: str) -> Path:
        normalized = Path(os.path.normpath(path).lstrip("/"))
        if not path or str(normalized) in {"", "."}:
            raise ValueError("Storage path cannot be empty")
        if normalized.is_absolute() or ".." in normalized.parts:
            raise ValueError("Invalid storage path")
        return normalized

    def _get_full_path(self, path: str) -> Path:
        relative_path = self._normalize_relative_path(path)
        full_path = (self.base_dir / relative_path).resolve()
        base_path = self.base_dir.resolve()
        if full_path != base_path and base_path not in full_path.parents:
            raise ValueError("Invalid storage path")
        return full_path

    def resolve_url(self, url: str) -> Path | None:
        prefix = f"{self.url_prefix}/"
        if not url or not url.startswith(prefix):
            return None
        try:
            return self._get_full_path(url[len(prefix):])
        except ValueError:
            return None

    def delete_url(self, url: str) -> bool:
        full_path = self.resolve_url(url)
        if not full_path or not full_path.exists():
            return False
        full_path.unlink()
        return True

    def save(self, file: BinaryIO, path: str) -> str:
        relative_path = self._normalize_relative_path(path)
        full_path = self._get_full_path(relative_path.as_posix())
        full_path.parent.mkdir(parents=True, exist_ok=True)

        with full_path.open("wb") as buffer:
            shutil.copyfileobj(file, buffer)

        return relative_path.as_posix()

    def delete(self, path: str) -> bool:
        try:
            full_path = self._get_full_path(path)
        except ValueError:
            return False
        if full_path.exists():
            full_path.unlink()
            return True
        return False

    def get_url(self, path: str) -> str:
        relative_path = self._normalize_relative_path(path)
        return f"{self.url_prefix}/{relative_path.as_posix()}"

    def exists(self, path: str) -> bool:
        try:
            return self._get_full_path(path).exists()
        except ValueError:
            return False

def get_storage() -> StorageInterface:
    return LocalStorage()

storage = get_storage()
