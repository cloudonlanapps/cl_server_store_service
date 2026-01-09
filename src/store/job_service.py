"""Job submission and management service for async compute tasks."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from .models import EntityJob

if TYPE_CHECKING:
    from cl_client import ComputeClient
    from cl_client.models import JobResponse

logger = logging.getLogger(__name__)


class JobSubmissionService:
    """Service for submitting and tracking async compute jobs."""

    db: Session
    compute_client: ComputeClient

    def __init__(self, db: Session, compute_client: ComputeClient) -> None:
        """Initialize job submission service.

        Args:
            db: Database session
            compute_client: ComputeClient instance for job submission
        """
        self.db = db
        self.compute_client = compute_client

    @staticmethod
    def _now_timestamp() -> int:
        """Get current timestamp in milliseconds.

        Returns:
            Current timestamp in milliseconds since epoch
        """
        return int(datetime.now(UTC).timestamp() * 1000)

    async def submit_face_detection(
        self,
        entity_id: int,
        file_path: str,
        on_complete_callback: Callable[[JobResponse], None],
    ) -> str | None:
        """Submit face detection job.

        Args:
            entity_id: Entity ID to associate with job
            file_path: Absolute path to image file
            on_complete_callback: Callback to invoke when job completes

        Returns:
            Job ID if successful, None if failed
        """
        try:
            job_response = await self.compute_client.face_detection.detect(
                image=Path(file_path),
                wait=False,
                on_complete=on_complete_callback,
            )

            now = self._now_timestamp()
            entity_job = EntityJob(
                entity_id=entity_id,
                job_id=job_response.job_id,
                task_type="face_detection",
                status="queued",
                created_at=now,
                updated_at=now,
            )
            self.db.add(entity_job)
            self.db.commit()

            logger.info(f"Submitted face_detection job {job_response.job_id} for entity {entity_id}")
            return job_response.job_id
        except Exception as e:
            logger.error(f"Failed to submit face_detection job for entity {entity_id}: {e}")
            self.db.rollback()
            return None

    async def submit_clip_embedding(
        self,
        entity_id: int,
        file_path: str,
        on_complete_callback: Callable[[JobResponse], None],
    ) -> str | None:
        """Submit CLIP embedding job.

        Args:
            entity_id: Entity ID to associate with job
            file_path: Absolute path to image file
            on_complete_callback: Callback to invoke when job completes

        Returns:
            Job ID if successful, None if failed
        """
        try:
            job_response = await self.compute_client.clip_embedding.embed_image(
                image=Path(file_path),
                wait=False,
                on_complete=on_complete_callback,
            )

            now = self._now_timestamp()
            entity_job = EntityJob(
                entity_id=entity_id,
                job_id=job_response.job_id,
                task_type="clip_embedding",
                status="queued",
                created_at=now,
                updated_at=now,
            )
            self.db.add(entity_job)
            self.db.commit()

            logger.info(f"Submitted clip_embedding job {job_response.job_id} for entity {entity_id}")
            return job_response.job_id
        except Exception as e:
            logger.error(f"Failed to submit clip_embedding job for entity {entity_id}: {e}")
            self.db.rollback()
            return None

    async def submit_face_embedding(
        self,
        face_id: int,
        entity_id: int,
        file_path: str,
        on_complete_callback: Callable[[JobResponse], None],
    ) -> str | None:
        """Submit face embedding job for a detected face.

        Args:
            face_id: Face record ID (used as entity_id in EntityJob for tracking)
            entity_id: Original image Entity ID (for reference/logging)
            file_path: Path to cropped face image
            on_complete_callback: MQTT callback when job completes

        Returns:
            Job ID if successful, None if failed
        """
        try:
            job_response = await self.compute_client.face_embedding.embed_faces(
                image=Path(file_path),
                wait=False,
                on_complete=on_complete_callback,
            )

            now = self._now_timestamp()
            # Use face_id as entity_id for tracking individual face jobs
            entity_job = EntityJob(
                entity_id=face_id,  # Track by face_id, not entity_id
                job_id=job_response.job_id,
                task_type="face_embedding",
                status="queued",
                created_at=now,
                updated_at=now,
            )
            self.db.add(entity_job)
            self.db.commit()

            logger.info(
                f"Submitted face_embedding job {job_response.job_id} "
                f"for face {face_id} (entity {entity_id})"
            )
            return job_response.job_id
        except Exception as e:
            logger.error(f"Failed to submit face_embedding job for face {face_id}: {e}")
            self.db.rollback()
            return None

    def delete_job_record(self, job_id: str) -> None:
        """Delete job record after successful completion.

        Args:
            job_id: Job ID to delete
        """
        try:
            entity_job = self.db.query(EntityJob).filter(EntityJob.job_id == job_id).first()
            if entity_job:
                self.db.delete(entity_job)
                self.db.commit()
                logger.debug(f"Deleted successful job record {job_id}")
        except Exception as e:
            logger.error(f"Failed to delete job record {job_id}: {e}")
            self.db.rollback()

    def update_job_status(
        self, job_id: str, status: str, error_message: str | None = None
    ) -> None:
        """Update job status in database.

        Args:
            job_id: Job ID to update
            status: New status (queued, in_progress, completed, failed)
            error_message: Optional error message if status is failed
        """
        try:
            entity_job = self.db.query(EntityJob).filter(EntityJob.job_id == job_id).first()
            if not entity_job:
                logger.warning(f"Job {job_id} not found in database")
                return

            entity_job.status = status
            entity_job.updated_at = self._now_timestamp()

            if status in ["completed", "failed"]:
                entity_job.completed_at = self._now_timestamp()

            if error_message:
                entity_job.error_message = error_message

            self.db.commit()
            logger.debug(f"Updated job {job_id} status to {status}")
        except Exception as e:
            logger.error(f"Failed to update job {job_id} status: {e}")
            self.db.rollback()
