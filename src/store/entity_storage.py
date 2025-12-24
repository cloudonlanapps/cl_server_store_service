"""Storage service for entity/media file management."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


class EntityStorageService:
    """Service for managing entity file storage with organized directory structure.

    Organizes files by date: store/YYYY/MM/DD/{md5}.{ext}
    """

    def __init__(self, base_dir: str):
        """
        Initialize entity storage service.

        Args:
            base_dir: Base directory for file storage.
        """
        self.base_dir: Path = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_storage_path(self, metadata: dict[str, str | int | float | None], original_filename: str) -> Path:
        """
        Generate organized file path based on metadata and current date.

        Structure: store/YYYY/MM/DD/{md5}.{ext}

        Args:
            metadata: File metadata dictionary containing md5
            original_filename: Original filename

        Returns:
            Path object for the file storage location
        """
        # Use current date for organization
        now = datetime.now(UTC)
        year = now.strftime("%Y")
        month = now.strftime("%m")
        day = now.strftime("%d")

        # Create directory structure with 'store' prefix
        dir_path = self.base_dir / "store" / year / month / day
        dir_path.mkdir(parents=True, exist_ok=True)

        # Generate filename with MD5 and extension
        md5_value = metadata.get("md5", "unknown")
        md5 = str(md5_value) if md5_value else "unknown"
        # Extract extension from original filename if not in metadata
        extension_value = metadata.get("extension")
        if extension_value:
            ext_str = str(extension_value)
            ext = f".{ext_str}" if not ext_str.startswith(".") else ext_str
        else:
            ext = Path(original_filename).suffix

        filename = f"{md5}{ext}"

        return dir_path / filename

    def save_file(
        self, file_bytes: bytes, metadata: dict[str, str | int | float | None], original_filename: str = "file"
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
        _ = file_path.write_bytes(file_bytes)

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
