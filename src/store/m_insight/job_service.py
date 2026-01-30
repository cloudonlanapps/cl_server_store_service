"""Job submission and management service for async compute tasks."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from store.broadcast_service.broadcaster import MInsightBroadcaster
    from store.broadcast_service.schemas import EntityStatusPayload

import asyncio
import threading
from datetime import UTC, datetime

from cl_client import ComputeClient
from cl_client.models import OnJobResponseCallback, JobResponse
from cl_ml_tools.utils.profiling import timed
from loguru import logger

from store.common.storage import StorageService
from store.db_service import (
    DBService,
    EntityIntelligenceData,
    JobInfo,
    EntitySchema,
    EntityVersionSchema,
    FaceSchema,
)

from store.broadcast_service.schemas import EntityStatusPayload


def make_once_only_callback(callback: OnJobResponseCallback) -> tuple[OnJobResponseCallback, asyncio.Lock]:
    """Wrap a callback to ensure it only executes once, even if called multiple times.

    This prevents race conditions when both MQTT and manual invocation trigger the same callback.

    Returns:
        Tuple of (wrapped_callback, lock) - lock can be used to check if callback already fired
    """
    executed = False
    lock = asyncio.Lock()

    async def wrapper(job: JobResponse) -> None:
        nonlocal executed
        async with lock:
            if executed:
                logger.debug(f"Callback for job {job.job_id} already executed, skipping duplicate call")
                return
            executed = True
        # Execute outside the lock to avoid holding it during callback execution
        await callback(job)

    return wrapper, lock


class JobSubmissionService:
    """Service for submitting and tracking async compute jobs."""

    compute_client: ComputeClient
    storage_service: StorageService
    broadcaster: "MInsightBroadcaster | None"
    db: DBService

    def __init__(
        self, 
        compute_client: ComputeClient, 
        storage_service: StorageService,
        broadcaster: "MInsightBroadcaster | None" = None,
        db: DBService | None = None
    ) -> None:
        """Initialize job submission service.

        Args:
            compute_client: ComputeClient instance for job submission
            storage_service: StorageService for file path resolution
            broadcaster: Optional broadcaster for status updates
            db: Optional DBService instance
        """
        self.compute_client = compute_client
        self.storage_service = storage_service
        self.broadcaster = broadcaster
        self.db = db or DBService()
        # Per-entity locks to serialize updates for the same entity
        self._entity_locks: dict[int, threading.Lock] = {}
        self._locks_lock = threading.Lock()

    def _get_entity_lock(self, entity_id: int) -> threading.Lock:
        """Get or create lock for specific entity.

        Args:
            entity_id: Entity ID

        Returns:
            threading.Lock for this entity
        """
        with self._locks_lock:
            if entity_id not in self._entity_locks:
                self._entity_locks[entity_id] = threading.Lock()
            return self._entity_locks[entity_id]

    @staticmethod
    def _now_timestamp() -> int:
        """Get current timestamp in milliseconds.

        Returns:
            Current timestamp in milliseconds since epoch
        """
        return int(datetime.now(UTC).timestamp() * 1000)

    def update_job_status(
        self,
        entity_id: int,
        job_id: str,
        status: str,
        error_message: str | None = None,
        completed_at: int | None = None
    ) -> None:
        """Update job status in Entity.intelligence_data.

        Args:
            entity_id: Entity ID being processed
            job_id: Job ID to update
            status: New job status (e.g., "completed", "failed")
            error_message: Optional error message if job failed
            completed_at: Optional completion timestamp from compute service
        """
        lock = self._get_entity_lock(entity_id)
        with lock:
            logger.debug(f"[update_job_status] Acquired lock for entity {entity_id}")
            self._update_job_status_locked(entity_id, job_id, status, error_message, completed_at)
            logger.debug(f"[update_job_status] Released lock for entity {entity_id}")

    def _update_job_status_locked(
        self,
        entity_id: int,
        job_id: str,
        status: str,
        error_message: str | None = None,
        completed_at: int | None = None
    ) -> None:
        """Internal method that performs the actual update (called with lock held)."""
        def update_fn(data):
            """Update function for atomic update."""
            logger.debug(
                f"[update_job_status] START - Entity {entity_id}, Job {job_id}: "
                f"Read from DB (with lock): face_embeddings={data.inference_status.face_embeddings}"
            )

            # Find and update job in active_jobs
            finished_job: JobInfo | None = None
            for job in data.active_jobs:
                if job.job_id == job_id:
                    job.status = status
                    job.completed_at = completed_at
                    job.error_message = error_message

                    # Update status in inference_status
                    if job.task_type == "face_detection":
                        data.inference_status.face_detection = status
                    elif job.task_type == "clip_embedding":
                        data.inference_status.clip_embedding = status
                    elif job.task_type == "dino_embedding":
                        data.inference_status.dino_embedding = status

                    # Store reference if finished
                    if status in ("completed", "failed"):
                        finished_job = job
                    break

            # Move to history if finished
            if finished_job:
                data.active_jobs = [j for j in data.active_jobs if j.job_id != job_id]
                data.job_history.append(finished_job)

            if error_message:
                data.error_message = error_message

            data.last_updated = self._now_timestamp()

            # Re-calculate overall status
            inf = data.inference_status

            # DEBUG LOGGING: Track face_embeddings state during updates
            task_type = finished_job.task_type if finished_job else "unknown"
            logger.debug(
                f"[update_job_status] Entity {entity_id}, Job {job_id} (task={task_type}, status={status}): "
                f"face_embeddings={inf.face_embeddings}, "
                f"face_detection={inf.face_detection}, "
                f"clip={inf.clip_embedding}, "
                f"dino={inf.dino_embedding}"
            )

            # 1. Collect all status fields that must be terminal
            all_statuses: list[str] = [
                inf.face_detection,
                inf.clip_embedding,
                inf.dino_embedding
            ]
            if inf.face_embeddings is not None and len(inf.face_embeddings) > 0:
                all_statuses.extend(inf.face_embeddings)

            # 2. Check terminal states
            # If we just finished face detection but haven't sent face embeddings yet,
            # face_embeddings list will be configured but all will be 'pending'.
            is_terminal = all(s in ("completed", "failed") for s in all_statuses)
            any_failed = any(s == "failed" for s in all_statuses)

            if is_terminal:
                data.overall_status = "failed" if any_failed else "completed"
            else:
                data.overall_status = "processing"

            logger.debug(
                f"[update_job_status] Entity {entity_id} overall status calculation: "
                f"all_statuses={all_statuses}, is_terminal={is_terminal}, overall={data.overall_status}"
            )

        try:
            # Perform atomic read-modify-write with row-level locking
            result = self.db.entity.atomic_update_intelligence_data(entity_id, update_fn)
            if not result:
                logger.warning(f"Entity {entity_id} not found or has no intelligence_data")
                return

            logger.debug(
                f"Updated job {job_id} for entity {entity_id} to status {status}. "
                f"Overall: {result.intelligence_data.overall_status if result.intelligence_data else 'unknown'}"
            )
            self.broadcast_entity_status(entity_id)

        except Exception as e:
            logger.error(f"Failed to update job {job_id} status for entity {entity_id}: {e}")


    def _register_job(self, entity: EntitySchema | EntityVersionSchema, job_id: str, task_type: str) -> None:
        """Helper to register an active job in the denormalized intelligence_data."""
        now = self._now_timestamp()

        # Check if entity exists first
        db_entity = self.db.entity.get(entity.id)
        if not db_entity:
            return

        # If no intelligence_data exists, create it first
        if not db_entity.intelligence_data:
            initial_data = EntityIntelligenceData(
                last_updated=now,
                active_processing_md5=db_entity.md5,
                overall_status="processing"
            )
            _ = self.db.entity.update_intelligence_data(entity.id, initial_data)

        # Now atomically update to add the job
        def add_job(data: EntityIntelligenceData):
            """Add job to active_jobs."""
            data.active_processing_md5 = db_entity.md5
            data.overall_status = "processing"

            if task_type == "face_detection":
                data.inference_status.face_detection = "processing"
            elif task_type == "clip_embedding":
                data.inference_status.clip_embedding = "processing"
            elif task_type == "dino_embedding":
                data.inference_status.dino_embedding = "processing"

            data.active_jobs.append(JobInfo(
                job_id=job_id,
                task_type=task_type,
                started_at=now,
                status="queued"
            ))
            data.last_updated = now

        _ = self.db.entity.atomic_update_intelligence_data(entity.id, add_job)

    def _register_failed_job(self, entity: EntitySchema | EntityVersionSchema, task_type: str, error_message: str) -> None:
        """Helper to register a failed job submission."""
        now = self._now_timestamp()
        db_entity = self.db.entity.get(entity.id)
        if not db_entity:
            return

        # If no intelligence_data exists, create it first
        if not db_entity.intelligence_data:
            initial_data = EntityIntelligenceData(
                last_updated=now,
                active_processing_md5=db_entity.md5,
                overall_status="failed"
            )
            _ = self.db.entity.update_intelligence_data(entity.id, initial_data)

        # Now atomically update to register failure
        def register_failure(data: EntityIntelligenceData):
            """Register failed job submission."""
            data.active_processing_md5 = db_entity.md5

            # Set specific task status to failed
            if task_type == "face_detection":
                data.inference_status.face_detection = "failed"
            elif task_type == "clip_embedding":
                data.inference_status.clip_embedding = "failed"
            elif task_type == "dino_embedding":
                data.inference_status.dino_embedding = "failed"

            data.error_message = error_message
            data.last_updated = now

            # Add to history
            data.job_history.append(JobInfo(
                job_id=f"failed_submission_{now}",
                task_type=task_type,
                started_at=now,
                status="failed",
                error_message=error_message,
                completed_at=now
            ))

            # Update overall status
            data.overall_status = "failed"

        _ = self.db.entity.atomic_update_intelligence_data(entity.id, register_failure)
        self.broadcast_entity_status(entity.id)

    @timed
    def _get_entity_status(self, entity_id: int) -> EntityStatusPayload | None:
        """Get status payload from denormalized field."""
        entity = self.db.entity.get(entity_id)
        if not entity or not entity.intelligence_data:
            return None

        # Convert dict to Pydantic model if it's a dict
        raw_data = entity.intelligence_data
        if isinstance(raw_data, dict):
            try:
                data = EntityIntelligenceData.model_validate(raw_data)
            except Exception:
                return None
        else:
            data = raw_data
        
        return EntityStatusPayload(
            entity_id=entity_id,
            status=data.overall_status,
            timestamp=data.last_updated,
            face_detection=data.inference_status.face_detection,
            face_count=data.face_count,
            clip_embedding=data.inference_status.clip_embedding,
            dino_embedding=data.inference_status.dino_embedding,
            face_embeddings=data.inference_status.face_embeddings,
        )

    def broadcast_entity_status(self, entity_id: int) -> None:
        """Public method to force a status broadcast for an entity."""
        if not self.broadcaster:
            return
            
        payload = self._get_entity_status(entity_id)
        if payload:
            # Set cleanup for final states
            clear_after = 60.0 if payload.status in ("completed", "failed") else None
            self.broadcaster.publish_entity_status(entity_id, payload, clear_after=clear_after)

    @timed
    async def submit_face_detection(
        self,
        entity: EntitySchema | EntityVersionSchema,
        on_complete_callback: OnJobResponseCallback,
    ) -> str | None:
        """Submit face detection job.

        Args:
            entity: EntitySchema or EntityVersionSchema object
            on_complete_callback: Callback to invoke when job completes

        Returns:
            Job ID if successful, None if failed
        """

        try:
            if not entity.file_path:
                logger.warning(f"Entity {entity.id} has no file_path")
                return None

            file_path = self.storage_service.get_absolute_path(entity.file_path)

            if not file_path.exists():
                logger.warning(f"File not found for entity {entity.id}: {file_path}")
                return None

            # Wrap callback to ensure it only executes once (prevents race condition)
            wrapped_callback, callback_lock = make_once_only_callback(on_complete_callback)

            job_response = await self.compute_client.face_detection.detect(
                image=file_path,
                wait=False,
                on_complete=wrapped_callback,
            )

            self._register_job(entity, job_response.job_id, "face_detection")
            logger.info(f"Submitted face_detection job {job_response.job_id} for entity {entity.id}")

            self.broadcast_entity_status(entity.id)

            # RACE CONDITION FIX: Check if job already completed (for very fast jobs)
            try:
                await asyncio.sleep(0.05)  # Small delay to allow MQTT to propagate
                full_job = await self.compute_client.get_job(job_response.job_id)
                if full_job and full_job.status in ("completed", "failed"):
                    logger.debug(f"Job {job_response.job_id} already completed, invoking callback manually")
                    await wrapped_callback(full_job)  # Use wrapped callback
            except Exception as e_check:
                logger.warning(f"Failed to check job status for {job_response.job_id}: {e_check}")

            return job_response.job_id

        except Exception as e:
            logger.error(f"Failed to submit face_detection job for entity {entity.id}: {e}")
            self._register_failed_job(entity, "face_detection", str(e))
            return None

    @timed
    async def submit_clip_embedding(
        self,
        entity: EntitySchema | EntityVersionSchema,
        on_complete_callback: OnJobResponseCallback,
    ) -> str | None:
        """Submit CLIP embedding job.

        Args:
            entity: EntitySchema or EntityVersionSchema object
            on_complete_callback: Callback to invoke when job completes

        Returns:
            Job ID if successful, None if failed
        """

        try:
            if not entity.file_path:
                return None
            file_path = self.storage_service.get_absolute_path(entity.file_path)

            # Wrap callback to ensure it only executes once (prevents race condition)
            wrapped_callback, callback_lock = make_once_only_callback(on_complete_callback)

            job_response = await self.compute_client.clip_embedding.embed_image(
                image=file_path,
                wait=False,
                on_complete=wrapped_callback,
            )

            self._register_job(entity, job_response.job_id, "clip_embedding")
            logger.info(f"Submitted clip_embedding job {job_response.job_id} for entity {entity.id}")

            self.broadcast_entity_status(entity.id)

            # RACE CONDITION FIX: Check if job already completed (for very fast jobs)
            try:
                await asyncio.sleep(0.05)  # Small delay to allow MQTT to propagate
                full_job = await self.compute_client.get_job(job_response.job_id)
                if full_job and full_job.status in ("completed", "failed"):
                    logger.debug(f"Job {job_response.job_id} already completed, invoking callback manually")
                    await wrapped_callback(full_job)  # Use wrapped callback
            except Exception as e_check:
                logger.warning(f"Failed to check job status for {job_response.job_id}: {e_check}")

            return job_response.job_id
        except Exception as e:
            logger.error(f"Failed to submit clip_embedding job for entity {entity.id}: {e}")
            self._register_failed_job(entity, "clip_embedding", str(e))
            return None

    @timed
    async def submit_dino_embedding(
        self,
        entity: EntitySchema | EntityVersionSchema,
        on_complete_callback: OnJobResponseCallback,
    ) -> str | None:
        """Submit DINOv2 embedding job.

        Args:
            entity: EntitySchema or EntityVersionSchema object
            on_complete_callback: Callback to invoke when job completes

        Returns:
            Job ID if successful, None if failed
        """

        try:
            if not entity.file_path:
                return None
            file_path = self.storage_service.get_absolute_path(entity.file_path)

            # Wrap callback to ensure it only executes once (prevents race condition)
            wrapped_callback, callback_lock = make_once_only_callback(on_complete_callback)

            job_response = await self.compute_client.dino_embedding.embed_image(
                image=file_path,
                wait=False,
                on_complete=wrapped_callback,
            )

            self._register_job(entity, job_response.job_id, "dino_embedding")
            logger.info(f"Submitted dino_embedding job {job_response.job_id} for entity {entity.id}")

            self.broadcast_entity_status(entity.id)

            # RACE CONDITION FIX: Check if job already completed (for very fast jobs)
            try:
                await asyncio.sleep(0.05)  # Small delay to allow MQTT to propagate
                full_job = await self.compute_client.get_job(job_response.job_id)
                if full_job and full_job.status in ("completed", "failed"):
                    logger.debug(f"Job {job_response.job_id} already completed, invoking callback manually")
                    await wrapped_callback(full_job)  # Use wrapped callback
            except Exception as e_check:
                logger.warning(f"Failed to check job status for {job_response.job_id}: {e_check}")

            return job_response.job_id
        except Exception as e:
            logger.error(f"Failed to submit dino_embedding job for entity {entity.id}: {e}")
            self._register_failed_job(entity, "dino_embedding", str(e))
            return None

    @timed
    async def submit_face_embedding(
        self,
        face: FaceSchema,
        entity: EntitySchema | EntityVersionSchema,
        on_complete_callback: OnJobResponseCallback,
    ) -> str | None:
        """Submit face embedding job for a detected face.

        Args:
            face: FaceSchema object
            entity: Parent Entity object (for tracking)
            on_complete_callback: MQTT callback when job completes

        Returns:
            Job ID if successful, None if failed
        """

        try:
            if not face.file_path:
                 return None

            file_path = self.storage_service.get_absolute_path(face.file_path)

            # Wrap callback to ensure it only executes once (prevents race condition)
            wrapped_callback, callback_lock = make_once_only_callback(on_complete_callback)

            job_response = await self.compute_client.face_embedding.embed_faces(
                image=file_path,
                wait=False,
                on_complete=wrapped_callback,
            )

            self._register_job(entity, job_response.job_id, "face_embedding")
            logger.info(f"Submitted face_embedding job {job_response.job_id} for face {face.id}")

            self.broadcast_entity_status(entity.id)

            # RACE CONDITION FIX: Check if job already completed (for very fast jobs)
            # to avoid missing MQTT callback
            try:
                await asyncio.sleep(0.05)  # Small delay to allow MQTT to propagate
                full_job = await self.compute_client.get_job(job_response.job_id)
                if full_job and full_job.status in ("completed", "failed"):
                    logger.debug(f"Job {job_response.job_id} already completed, invoking callback manually")
                    await wrapped_callback(full_job)  # Use wrapped callback
            except Exception as e:
                logger.warning(f"Failed to check job status for {job_response.job_id}: {e}")

            return job_response.job_id
        except Exception as e:
            logger.error(f"Failed to submit face_embedding job for face {face.id}: {e}")
            # Note: face embedding failure doesn't necessarily fail the whole entity,
            # but we should probably record it. However, face embedding structure is distinct.
            # Tracking validation: face_embeddings status is a list.
            # For now, relying on log for face embedding specific failure to avoid complexity with list indices.
            return None
