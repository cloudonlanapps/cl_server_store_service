"""Compute job services."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from cl_server_shared import Config, JobStorageService
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from . import schemas
from .models import Job


class JobService:
    """Service layer for job management."""

    def __init__(self, db: Session):
        """Initialize the job service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        # Use the module-level repository_adapter (allows test patching)
        from .. import repository_adapter

        self.repository = repository_adapter
        # Use COMPUTE_STORAGE_DIR for job files (organized per job)
        self.file_storage = JobStorageService(base_dir=Config.COMPUTE_STORAGE_DIR)
        self.storage_base = Path(Config.COMPUTE_STORAGE_DIR)

    def get_job(self, job_id: str):
        """Get job status and results.

        Args:
            job_id: Unique job identifier

        Returns:
            JobResponse with job details

        Raises:
            ValueError: If job not found
        """
        # Get additional metadata from database
        db_job = self.db.query(Job).filter_by(job_id=job_id).first()
        if not db_job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found"
            )
        library_job = db_job

        return schemas.JobResponse(
            job_id=library_job.job_id,
            task_type=library_job.task_type,
            status=library_job.status,
            progress=library_job.progress,
            params=json.loads(library_job.params),  # Already parsed by repository
            task_output=json.loads(library_job.task_output)
            if library_job.task_output
            else None,  # Already parsed by repository
            created_at=db_job.created_at,
            updated_at=db_job.created_at,
            started_at=db_job.started_at,
            completed_at=db_job.completed_at,
            error_message=library_job.error_message,
            priority=db_job.priority,
        )

    def delete_job(self, job_id: str) -> None:
        """Delete job and all associated files.

        Args:
            job_id: Unique job identifier

        Raises:
            HTTPException: If job not found
        """
        # Check job exists using repository
        library_job = self.repository.get_job(job_id)
        if not library_job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found"
            )

        # Delete job directory using JobStorage protocol method
        self.file_storage.remove(job_id)

        # Use repository to delete job (handles QueueEntry cascade)
        self.repository.delete_job(job_id)

    def get_storage_size(self):
        """Get total storage usage for all jobs.

        Returns:
            StorageInfo with storage details
        """
        # Calculate storage size directly
        jobs_dir = self.storage_base / "jobs"
        total_size = 0
        job_count = 0

        if jobs_dir.exists():
            for job_dir in jobs_dir.iterdir():
                if job_dir.is_dir():
                    job_count += 1
                    for file_path in job_dir.rglob("*"):
                        if file_path.is_file():
                            total_size += file_path.stat().st_size

        storage_info = {
            "total_size": total_size,
            "job_count": job_count,
        }
        return schemas.StorageInfo(**storage_info)

    def cleanup_old_jobs(self, days: int):
        """Clean up jobs older than specified number of days.

        Args:
            days: Number of days threshold

        Returns:
            CleanupResult with cleanup details
        """
        import time

        # Calculate cleanup info directly
        jobs_dir = self.storage_base / "jobs"
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

                        # Delete job using JobStorage protocol method
                        self.file_storage.remove(job_dir.name)
                        deleted_count += 1

        # Remove cleaned up jobs from database using repository
        current_time_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        cutoff_time_ms = current_time_ms - (days * 24 * 60 * 60 * 1000)

        old_jobs = self.db.query(Job).filter(Job.created_at < cutoff_time_ms).all()
        for job in old_jobs:
            # Use repository to delete (handles QueueEntry cascade)
            self.repository.delete_job(job.job_id)

        cleanup_info = {
            "deleted_count": deleted_count,
            "freed_space": freed_space,
        }
        return schemas.CleanupResult(**cleanup_info)


class CapabilityService:
    """Service layer for worker capability management."""

    def __init__(self, db: Session):
        """Initialize capability service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def get_available_capabilities(self) -> dict:
        """Get aggregated available worker capabilities.

        Returns:
            Dict mapping capability names to available idle count
            Example: {"image_resize": 2, "image_conversion": 1}
        """
        try:
            from .capability_manager import get_capability_manager

            manager = get_capability_manager()
            return manager.get_cached_capabilities()
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Error retrieving worker capabilities: {e}")
            return {}

    def get_worker_count(self) -> int:
        """Get total number of connected workers.

        Returns:
            Number of unique workers in the capability cache
        """
        try:
            from .capability_manager import get_capability_manager

            manager = get_capability_manager()
            return len(manager.capabilities_cache)
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Error retrieving worker count: {e}")
            return 0
