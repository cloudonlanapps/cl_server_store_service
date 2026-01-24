"""Job submission and management service for async compute tasks."""

from __future__ import annotations

from datetime import UTC, datetime

from cl_client import ComputeClient
from cl_client.models import OnJobResponseCallback
from cl_ml_tools.utils.profiling import timed
from loguru import logger

from store.common import Entity, EntityJob, Face, database
from store.common.database import with_retry
from store.common.storage import StorageService

from .schemas import EntityVersionData


class JobSubmissionService:
    """Service for submitting and tracking async compute jobs."""

    compute_client: ComputeClient
    storage_service: StorageService

    def __init__(self, compute_client: ComputeClient, storage_service: StorageService) -> None:
        """Initialize job submission service.

        Args:
            compute_client: ComputeClient instance for job submission
            storage_service: StorageService for file path resolution
        """
        self.compute_client = compute_client
        self.storage_service = storage_service

    @staticmethod
    def _now_timestamp() -> int:
        """Get current timestamp in milliseconds.

        Returns:
            Current timestamp in milliseconds since epoch
        """
        return int(datetime.now(UTC).timestamp() * 1000)

    def update_job_status(self, job_id: str, status: str, error_message: str | None = None) -> None:
        """Update job status in entity_jobs table.

        Args:
            job_id: Job ID to update
            status: New job status (e.g., "completed", "failed")
            error_message: Optional error message if job failed
        """
        @with_retry(max_retries=10)
        def do_update():
            db = database.SessionLocal()
            try:
                entity_job = db.query(EntityJob).filter(EntityJob.job_id == job_id).first()
                if not entity_job:
                    logger.warning(f"Job {job_id} not found in entity_jobs table")
                    return

                entity_job.status = status
                entity_job.updated_at = JobSubmissionService._now_timestamp()

                if status in ("completed", "failed"):
                    entity_job.completed_at = JobSubmissionService._now_timestamp()

                if error_message:
                    entity_job.error_message = error_message

                db.commit()
                logger.debug(f"Updated job {job_id} status to {status}")
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        try:
            do_update()
        except Exception as e:
            logger.error(f"Failed to update job {job_id} status: {e}")

    def delete_job_record(self, job_id: str) -> None:
        """Delete job record from entity_jobs table.

        Args:
            job_id: Job ID to delete
        """
        @with_retry(max_retries=10)
        def do_delete():
            db = database.SessionLocal()
            try:
                entity_job = db.query(EntityJob).filter(EntityJob.job_id == job_id).first()
                if entity_job:
                    db.delete(entity_job)
                    db.commit()
                    logger.debug(f"Deleted job record {job_id}")
                else:
                    logger.warning(f"Job {job_id} not found for deletion")
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        try:
            do_delete()
        except Exception as e:
            logger.error(f"Failed to delete job record {job_id}: {e}")





    @timed
    async def submit_face_detection(
        self,
        entity: Entity | EntityVersionData,
        on_complete_callback: OnJobResponseCallback,
    ) -> str | None:
        """Submit face detection job.

        Args:
            entity: Entity or EntityVersionData object
            on_complete_callback: Callback to invoke when job completes

        Returns:
            Job ID if successful, None if failed
        """

        try:
            # Resolve file path using StorageService
            # Both Entity and EntityVersionData should support get_file_path(storage_service)
            # Note: Entity model currently has get_file_path? No, Face has it.
            # I need to ensure Entity has it or use logic here.
            # EntityVersionData has it (added in schemas.py).
            # Entity model (in models.py) DOES NOT have it yet?
            # Let's check if I added it. I added it to Face.
            # If entity is passed, I might need to manual resolve or add helper.
            # However, logic is consistent: storage_service.get_absolute_path(entity.file_path)

            if not entity.file_path:
                logger.warning(f"Entity {entity.id} has no file_path")
                return None

            file_path = self.storage_service.get_absolute_path(entity.file_path)

            if not file_path.exists():
                logger.warning(f"File not found for entity {entity.id}: {file_path}")
                return None

            job_response = await self.compute_client.face_detection.detect(
                image=file_path,
                wait=False,
                on_complete=on_complete_callback,
            )

            @with_retry(max_retries=10)
            def save_job():
                db = database.SessionLocal()
                try:
                    now = self._now_timestamp()
                    entity_job = EntityJob(
                        entity_id=entity.id,
                        job_id=job_response.job_id,
                        task_type="face_detection",
                        status="queued",
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(entity_job)
                    db.commit()
                    logger.info(
                        f"Submitted face_detection job {job_response.job_id} for entity {entity.id}"
                    )
                except Exception:
                    db.rollback()
                    raise
                finally:
                    db.close()

            save_job()
            return job_response.job_id

        except Exception as e:
            logger.error(f"Failed to submit face_detection job for entity {entity.id}: {e}")
            return None

    @timed
    async def submit_clip_embedding(
        self,
        entity: Entity | EntityVersionData,
        on_complete_callback: OnJobResponseCallback,
    ) -> str | None:
        """Submit CLIP embedding job.

        Args:
            entity: Entity or EntityVersionData object
            on_complete_callback: Callback to invoke when job completes

        Returns:
            Job ID if successful, None if failed
        """

        try:
            if not entity.file_path:
                return None
            file_path = self.storage_service.get_absolute_path(entity.file_path)

            job_response = await self.compute_client.clip_embedding.embed_image(
                image=file_path,
                wait=False,
                on_complete=on_complete_callback,
            )

            @with_retry(max_retries=10)
            def save_job():
                db = database.SessionLocal()
                try:
                    now = self._now_timestamp()
                    entity_job = EntityJob(
                        entity_id=entity.id,
                        job_id=job_response.job_id,
                        task_type="clip_embedding",
                        status="queued",
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(entity_job)
                    db.commit()
                    logger.info(
                        f"Submitted clip_embedding job {job_response.job_id} for entity {entity.id}"
                    )
                except Exception:
                    db.rollback()
                    raise
                finally:
                    db.close()

            save_job()
            return job_response.job_id
        except Exception as e:
            logger.error(f"Failed to submit clip_embedding job for entity {entity.id}: {e}")
            return None

    @timed
    async def submit_dino_embedding(
        self,
        entity: Entity | EntityVersionData,
        on_complete_callback: OnJobResponseCallback,
    ) -> str | None:
        """Submit DINOv2 embedding job.

        Args:
            entity: Entity or EntityVersionData object
            on_complete_callback: Callback to invoke when job completes

        Returns:
            Job ID if successful, None if failed
        """

        try:
            if not entity.file_path:
                return None
            file_path = self.storage_service.get_absolute_path(entity.file_path)

            job_response = await self.compute_client.dino_embedding.embed_image(
                image=file_path,
                wait=False,
                on_complete=on_complete_callback,
            )

            @with_retry(max_retries=10)
            def save_job():
                db = database.SessionLocal()
                try:
                    now = self._now_timestamp()
                    entity_job = EntityJob(
                        entity_id=entity.id,
                        job_id=job_response.job_id,
                        task_type="dino_embedding",
                        status="queued",
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(entity_job)
                    db.commit()
                    logger.info(
                        f"Submitted dino_embedding job {job_response.job_id} for entity {entity.id}"
                    )
                except Exception:
                    db.rollback()
                    raise
                finally:
                    db.close()

            save_job()
            return job_response.job_id
        except Exception as e:
            logger.error(f"Failed to submit dino_embedding job for entity {entity.id}: {e}")
            return None

    @timed
    async def submit_face_embedding(
        self,
        face: Face,
        entity: Entity | EntityVersionData,
        on_complete_callback: OnJobResponseCallback,
    ) -> str | None:
        """Submit face embedding job for a detected face.

        Args:
            face: Face object
            entity: Parent Entity object (for tracking)
            on_complete_callback: MQTT callback when job completes

        Returns:
            Job ID if successful, None if failed
        """

        try:
            # Resolve face file path
            # Face model has get_file_path(storage_service)
            file_path = face.get_file_path(self.storage_service)

            job_response = await self.compute_client.face_embedding.embed_faces(
                image=file_path,
                wait=False,
                on_complete=on_complete_callback,
            )

            @with_retry(max_retries=10)
            def save_job():
                db = database.SessionLocal()
                try:
                    now = self._now_timestamp()
                    # Track face_embedding jobs under the parent entity
                    entity_job = EntityJob(
                        entity_id=entity.id,  # Use parent entity_id
                        job_id=job_response.job_id,
                        task_type="face_embedding",
                        status="queued",
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(entity_job)
                    db.commit()
                    logger.info(
                        f"Submitted face_embedding job {job_response.job_id} "
                        + f"for face {face.id} (entity {entity.id})"
                    )
                except Exception:
                    db.rollback()
                    raise
                finally:
                    db.close()

            save_job()
            return job_response.job_id
        except Exception as e:
            logger.error(f"Failed to submit face_embedding job for face {face.id}: {e}")
            return None

        @with_retry(max_retries=10)
        def do_delete():
            db = database.SessionLocal()
            try:
                entity_job = db.query(EntityJob).filter(EntityJob.job_id == job_id).first()
                if entity_job:
                    db.delete(entity_job)
                    db.commit()
                    logger.debug(f"Deleted successful job record {job_id}")
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        try:
            do_delete()
        except Exception as e:
            logger.error(f"Failed to delete job record {job_id}: {e}")

        @with_retry(max_retries=10)
        def do_update():
            db = database.SessionLocal()
            try:
                entity_job = db.query(EntityJob).filter(EntityJob.job_id == job_id).first()
                if not entity_job:
                    logger.warning(f"Job {job_id} not found in database")
                    return

                entity_job.status = status
                entity_job.updated_at = self._now_timestamp()

                if status in ["completed", "failed"]:
                    entity_job.completed_at = self._now_timestamp()

                if error_message:
                    entity_job.error_message = error_message

                db.commit()
                logger.debug(f"Updated job {job_id} status to {status}")
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        try:
            do_update()
        except Exception as e:
            logger.error(f"Failed to update job {job_id} status: {e}")
