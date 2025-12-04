from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import UploadFile


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

        Structure: store/YYYY/MM/DD/{md5}.{ext}

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

        # Create directory structure with 'store' prefix
        dir_path = self.base_dir / "store" / year / month / day
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

    # Job file management functions (from compute service, decoupled from endpoints)

    def create_job_directory(self, job_id: str) -> Path:
        """Create job-specific directory structure.

        Args:
            job_id: Unique job identifier

        Returns:
            Path to the job directory
        """
        job_dir = self.base_dir / "jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "input").mkdir(exist_ok=True)
        (job_dir / "output").mkdir(exist_ok=True)
        return job_dir

    def get_job_path(self, job_id: str) -> Path:
        """Get the job directory path.

        Args:
            job_id: Unique job identifier

        Returns:
            Path to the job directory
        """
        return self.base_dir / "jobs" / job_id

    def get_input_path(self, job_id: str) -> Path:
        """Get the input directory path for a job.

        Args:
            job_id: Unique job identifier

        Returns:
            Path to the input directory
        """
        return self.base_dir / "jobs" / job_id / "input"

    def get_output_path(self, job_id: str) -> Path:
        """Get the output directory path for a job.

        Args:
            job_id: Unique job identifier

        Returns:
            Path to the output directory
        """
        return self.base_dir / "jobs" / job_id / "output"

    async def save_input_file(
        self,
        job_id: str,
        filename: str,
        file: UploadFile,
    ) -> dict:
        """Save uploaded input file and return file info.

        Args:
            job_id: Unique job identifier
            filename: Name of the file
            file: Uploaded file object

        Returns:
            Dictionary with file information
        """
        input_dir = self.get_input_path(job_id)
        file_path = input_dir / filename

        # Write file in chunks
        with open(file_path, "wb") as f:
            contents = await file.read()
            f.write(contents)

        # Calculate file info
        file_size = file_path.stat().st_size
        file_hash = self._calculate_hash(file_path)

        return {
            "filename": filename,
            "path": str(file_path.relative_to(self.base_dir)),
            "size": file_size,
            "hash": file_hash,
        }

    def create_external_symlink(
        self,
        job_id: str,
        external_path: str,
        link_name: Optional[str] = None,
    ) -> str:
        """Create symlink to external file in job input directory.

        Args:
            job_id: Unique job identifier
            external_path: Path to external file
            link_name: Name for the link (defaults to basename of external_path)

        Returns:
            Relative path to the symlink
        """
        input_dir = self.get_input_path(job_id)

        # Use basename of external path if no link name provided
        if link_name is None:
            link_name = Path(external_path).name

        link_path = input_dir / link_name

        # Remove existing link if present
        if link_path.exists() or link_path.is_symlink():
            link_path.unlink()

        # Create symlink
        os.symlink(external_path, link_path)

        return str(link_path.relative_to(self.base_dir))

    def cleanup_job(self, job_id: str) -> bool:
        """Delete entire job directory and all its files.

        Args:
            job_id: Unique job identifier

        Returns:
            True if deleted, False otherwise
        """
        job_dir = self.get_job_path(job_id)
        if job_dir.exists():
            shutil.rmtree(job_dir)
            return True
        return False

    def get_storage_size(self) -> dict:
        """Calculate total storage usage for all jobs.

        Returns:
            Dictionary with storage information
        """
        jobs_dir = self.base_dir / "jobs"
        total_size = 0
        job_count = 0

        if jobs_dir.exists():
            for job_dir in jobs_dir.iterdir():
                if job_dir.is_dir():
                    job_count += 1
                    for file_path in job_dir.rglob("*"):
                        if file_path.is_file():
                            total_size += file_path.stat().st_size

        return {
            "total_size": total_size,
            "job_count": job_count,
        }

    def cleanup_old_jobs(self, days: int) -> dict:
        """Delete jobs older than specified number of days.

        Args:
            days: Number of days threshold

        Returns:
            Dictionary with cleanup results
        """
        jobs_dir = self.base_dir / "jobs"
        current_time = time.time()
        cutoff_time = current_time - (days * 24 * 60 * 60)
        deleted_count = 0
        freed_space = 0

        if jobs_dir.exists():
            for job_dir in jobs_dir.iterdir():
                if job_dir.is_dir():
                    # Check modification time
                    dir_mtime = job_dir.stat().st_mtime
                    if dir_mtime < cutoff_time:
                        # Calculate size before deletion
                        for file_path in job_dir.rglob("*"):
                            if file_path.is_file():
                                freed_space += file_path.stat().st_size

                        # Delete job
                        self.cleanup_job(job_dir.name)
                        deleted_count += 1

        return {
            "deleted_count": deleted_count,
            "freed_space": freed_space,
        }

    @staticmethod
    def _calculate_hash(file_path: Path, algorithm: str = "sha256") -> str:
        """Calculate file hash.

        Args:
            file_path: Path to the file
            algorithm: Hash algorithm (default: sha256)

        Returns:
            Hexadecimal hash string
        """
        hash_obj = hashlib.new(algorithm)
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()
