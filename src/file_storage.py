from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class FileStorageService:
    """Service for managing file storage with organized directory structure."""

    def __init__(self, base_dir: Optional[str] = None):
        """
        Initialize file storage service.

        Args:
            base_dir: Base directory for file storage. If None, uses MEDIA_STORAGE_DIR from config.
        """
        if base_dir is None:
            from .config import MEDIA_STORAGE_DIR

            base_dir = MEDIA_STORAGE_DIR

        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_storage_path(self, metadata: dict, original_filename: str) -> Path:
        """
        Generate organized file path based on metadata and current date.

        Structure: YYYY/MM/DD/{md5}.{ext}

        Args:
            metadata: File metadata dictionary containing md5
            original_filename: Original filename

        Returns:
            Path object for the file storage location
        """
        # Use current date for organization
        now = datetime.now(timezone.utc)
        year = now.strftime("%Y")
        month = now.strftime("%m")
        day = now.strftime("%d")

        # Create directory structure
        dir_path = self.base_dir / year / month / day
        dir_path.mkdir(parents=True, exist_ok=True)

        # Generate filename with MD5 and extension
        md5 = metadata.get("md5", "unknown")
        # Extract extension from original filename if not in metadata
        if "extension" in metadata and metadata["extension"]:
            ext = (
                f".{metadata['extension']}"
                if not metadata["extension"].startswith(".")
                else metadata["extension"]
            )
        else:
            ext = Path(original_filename).suffix

        filename = f"{md5}{ext}"

        return dir_path / filename

    def save_file(
        self, file_bytes: bytes, metadata: dict, original_filename: str = "file"
    ) -> str:
        """
        Save file to storage with organized directory structure.

        Args:
            file_bytes: File content as bytes
            metadata: File metadata dictionary
            original_filename: Original filename

        Returns:
            Relative path to the saved file
        """
        # Get storage path
        file_path = self.get_storage_path(metadata, original_filename)

        # Write file
        file_path.write_bytes(file_bytes)

        # Return relative path from base_dir
        return str(file_path.relative_to(self.base_dir))

    def delete_file(self, relative_path: str) -> bool:
        """
        Delete file from storage.

        Args:
            relative_path: Relative path to the file

        Returns:
            True if file was deleted, False otherwise
        """
        if not relative_path:
            return False

        file_path = self.base_dir / relative_path

        try:
            if file_path.exists():
                file_path.unlink()

                # Clean up empty directories
                self._cleanup_empty_dirs(file_path.parent)
                return True
        except Exception as e:
            print(f"Error deleting file {relative_path}: {e}")

        return False

    def _cleanup_empty_dirs(self, dir_path: Path) -> None:
        """
        Remove empty parent directories up to base_dir.

        Args:
            dir_path: Directory to start cleanup from
        """
        try:
            # Don't remove base_dir itself
            while dir_path != self.base_dir and dir_path.exists():
                if not any(dir_path.iterdir()):
                    dir_path.rmdir()
                    dir_path = dir_path.parent
                else:
                    break
        except Exception:
            pass  # Ignore errors during cleanup

    def get_absolute_path(self, relative_path: str) -> Path:
        """
        Get absolute path from relative path.

        Args:
            relative_path: Relative path to the file

        Returns:
            Absolute Path object
        """
        return self.base_dir / relative_path
