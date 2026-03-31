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
    def __init__(self, base_dir: str = settings.upload_dir):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_full_path(self, path: str) -> Path:
        # Prevent path traversal
        normalized_path = os.path.normpath(path).lstrip("/")
        return self.base_dir / normalized_path

    def save(self, file: BinaryIO, path: str) -> str:
        full_path = self._get_full_path(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        with full_path.open("wb") as buffer:
            shutil.copyfileobj(file, buffer)
        
        return path

    def delete(self, path: str) -> bool:
        full_path = self._get_full_path(path)
        if full_path.exists():
            full_path.unlink()
            return True
        return False

    def get_url(self, path: str) -> str:
        # In this app, /uploads is mounted as StaticFiles
        return f"/uploads/{path.lstrip('/')}"

    def exists(self, path: str) -> bool:
        return self._get_full_path(path).exists()

def get_storage() -> StorageInterface:
    # Future-ready: check settings for S3 vs Local
    # if settings.storage_type == "s3":
    #     return S3Storage(...)
    return LocalStorage()

storage = get_storage()
