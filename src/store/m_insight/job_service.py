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
        logger.info(f"[TRACE] make_once_only_callback wrapper invoked: job_id={job.job_id}, status={job.status}")
        async with lock:
            if executed:
                logger.debug(f"Callback for job {job.job_id} already executed, skipping duplicate call")
                return
            executed = True
        # Execute outside the lock to avoid holding it during callback execution
        logger.info(f"[TRACE] Executing callback for job_id={job.job_id}")
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
        def update_fn(data: EntityIntelligenceData):
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
                    elif job.task_type == "hls_streaming":
                        data.inference_status.hls_streaming = status
                    elif job.task_type == "face_embedding":
                        # Individual face_embeddings in data.inference_status.face_embeddings 
                        # are updated via JobCallbackHandler.handle_face_embedding_complete.
                        # We just need to ensure the job remains matched here so it's moved to history.
                        pass

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
                f"dino={inf.dino_embedding}, "
                f"hls={inf.hls_streaming}"
            )

            # 1. Collect all status fields that must be terminal
            all_statuses: list[str] = [
                inf.face_detection,
                inf.clip_embedding,
                inf.dino_embedding,
                inf.hls_streaming
            ]
            if inf.face_embeddings is not None and len(inf.face_embeddings) > 0:
                all_statuses.extend(inf.face_embeddings)

            # 2. Check terminal states
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
            result = self.db.intelligence.atomic_update_intelligence_data(entity_id, update_fn)
            if not result:
                logger.warning(f"Entity {entity_id} not found or has no intelligence_data")
                return

            logger.debug(
                f"Updated job {job_id} for entity {entity_id} to status {status}. "
                f"Overall: {result.overall_status}"
            )
            self.broadcast_entity_status(entity_id)

        except Exception as e:
            logger.error(f"Failed to update job {job_id} status for entity {entity_id}: {e}")

    def update_job_progress(self, entity_id: int, job_id: str, progress: int) -> None:
        """Update job progress in Entity.intelligence_data.
        
        Args:
            entity_id: Entity ID being processed
            job_id: Job ID to update
            progress: New progress (0-100)
        """
        lock = self._get_entity_lock(entity_id)
        with lock:
            self._update_job_progress_locked(entity_id, job_id, progress)

    def _update_job_progress_locked(self, entity_id: int, job_id: str, progress: int) -> None:
        """Internal method for updating job progress (called with lock held)."""
        def update_fn(data: EntityIntelligenceData):
            for job in data.active_jobs:
                if job.job_id == job_id:
                    job.progress = progress
                    # SIGNAL EARLY AVAILABILITY:
                    # If HLS streaming reports ANY progress, it means the manifest is ready.
                    if job.task_type == "hls_streaming" and progress > 0:
                        # Only set to available if not already completed/failed
                        if data.inference_status.hls_streaming not in ("completed", "failed"):
                            data.inference_status.hls_streaming = "available"
                    break
        
        self.db.intelligence.atomic_update_intelligence_data(entity_id, update_fn)
        self.broadcast_entity_status(entity_id)


    def delete_job_record(self, entity_id: int, job_id: str) -> None:
        """Remove a job record from active_jobs.

        Used when a job is no longer relevant (e.g. entity MD5 changed).

        Args:
            entity_id: Entity ID
            job_id: Job ID to remove
        """
        def remove_job(data: EntityIntelligenceData):
            """Remove job from active_jobs."""
            initial_count = len(data.active_jobs)
            data.active_jobs = [j for j in data.active_jobs if j.job_id != job_id]
            if len(data.active_jobs) != initial_count:
                data.last_updated = self._now_timestamp()

        _ = self.db.intelligence.atomic_update_intelligence_data(entity_id, remove_job)
        self.broadcast_entity_status(entity_id)


    def _register_job(self, entity: EntitySchema | EntityVersionSchema, job_id: str, task_type: str) -> None:
        """Helper to register an active job in the denormalized intelligence_data."""
        logger.info(f"[TRACE] _register_job: entity_id={entity.id}, job_id={job_id}, task_type={task_type}")
        now = self._now_timestamp()

        # Check if entity exists first
        db_entity = self.db.entity.get(entity.id)
        if not db_entity:
            logger.warning(f"[TRACE] _register_job: entity {entity.id} not found in DB!")
            return

        logger.info(f"[TRACE] _register_job: DB entity found - id={db_entity.id}, md5={db_entity.md5}, file_path={db_entity.file_path}")

        # If no intelligence_data exists, create it first
        if not self.db.intelligence.get_intelligence_data(entity.id):
            initial_data = EntityIntelligenceData(
                last_updated=now,
                active_processing_md5=db_entity.md5,
                overall_status="processing"
            )
            logger.info(f"[TRACE] _register_job: Creating initial intelligence_data for entity_id={entity.id}")
            _ = self.db.intelligence.update_intelligence_data(entity.id, initial_data)

        # Now atomically update to add the job
        def add_job(data: EntityIntelligenceData):
            """Add job to active_jobs."""
            # Track current MD5 to prevent race conditions if file changes during processing
            data.active_processing_md5 = db_entity.md5
            data.overall_status = "processing"

            if task_type == "face_detection":
                data.inference_status.face_detection = "processing"
            elif task_type == "clip_embedding":
                data.inference_status.clip_embedding = "processing"
            elif task_type == "dino_embedding":
                data.inference_status.dino_embedding = "processing"
            elif task_type == "hls_streaming":
                data.inference_status.hls_streaming = "processing"

            # Check if this job is already in active_jobs (to avoid duplicates if called twice rapidly)
            if not any(j.job_id == job_id for j in data.active_jobs):
                data.active_jobs.append(JobInfo(
                    job_id=job_id,
                    task_type=task_type,
                    started_at=now,
                    status="queued"
                ))
            data.last_updated = now

        _ = self.db.intelligence.atomic_update_intelligence_data(entity.id, add_job)

    def _register_failed_job(self, entity: EntitySchema | EntityVersionSchema, task_type: str, error_message: str) -> None:
        """Helper to register a failed job submission."""
        now = self._now_timestamp()
        db_entity = self.db.entity.get(entity.id)
        if not db_entity:
            return

        # If no intelligence_data exists, create it first
        if not self.db.intelligence.get_intelligence_data(entity.id):
            initial_data = EntityIntelligenceData(
                last_updated=now,
                active_processing_md5=db_entity.md5,
                overall_status="failed"
            )
            _ = self.db.intelligence.update_intelligence_data(entity.id, initial_data)

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

        _ = self.db.intelligence.atomic_update_intelligence_data(entity.id, register_failure)
        self.broadcast_entity_status(entity.id)

    @timed
    def _get_entity_status(self, entity_id: int) -> EntityStatusPayload | None:
        """Get status payload from denormalized field."""
        # entity = self.db.entity.get(entity_id) # Not needed if we only need status
        # but we might want to check existence check if strict
        
        data = self.db.intelligence.get_intelligence_data(entity_id)
        if not data:
            return None
        
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

    def _should_skip_submission_locked(
        self,
        entity: EntitySchema | EntityVersionSchema,
        task_type: str,
    ) -> str | None:
        """Centralized check to see if a job should be skipped.
        
        Must be called with entity lock held.
        
        Returns:
            Job ID if an active job already exists.
            'ready' if the task is already completed for the current MD5.
            None if submission should proceed.
        """
        entity_id = entity.id
        intel_data = self.db.intelligence.get_intelligence_data(entity_id)
        
        if not intel_data:
            return None

        # 1. Check current status for this task type
        # Special handling for face_embedding as it's a list of statuses
        if task_type == "face_embedding":
            # If there are any face embeddings, and all are completed/failed, consider it done
            if intel_data.inference_status.face_embeddings and \
               all(s in ("completed", "failed") for s in intel_data.inference_status.face_embeddings):
                if intel_data.last_processed_md5 == entity.md5:
                    logger.info(f"{task_type} already completed for MD5 {entity.md5}, skipping.")
                    return "ready"
            # If any face embedding is still processing, consider it active
            if intel_data.inference_status.face_embeddings and \
               any(s in ("pending", "processing", "running") for s in intel_data.inference_status.face_embeddings):
                for job in intel_data.active_jobs:
                    if job.task_type == task_type:
                        logger.info(f"{task_type} job already active for entity {entity_id}: {job.job_id}")
                        return job.job_id
            # If no face embeddings, or all are terminal but MD5 changed, proceed
            return None
        
        status = getattr(intel_data.inference_status, task_type, None)
        
        # Mapping statuses that count as "already being handled"
        if status in ("pending", "processing", "running", "available"):
            # Check if there is an actual active job
            for job in intel_data.active_jobs:
                if job.task_type == task_type:
                    logger.info(f"{task_type} job already active for entity {entity_id}: {job.job_id}")
                    return job.job_id
            
            # Special case for available status: it means work is done enough for consumption
            if status == "available":
                logger.debug(f"{task_type} already available/ready for entity {entity_id}")
                return "ready"

        # 2. Check if already completed for same MD5
        if status == "completed" and intel_data.last_processed_md5 == entity.md5:
            logger.info(f"{task_type} already completed for MD5 {entity.md5}, skipping.")
            return "ready"

        return None

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

        entity_id = entity.id
        logger.info(f"[TRACE] submit_face_detection called: entity_id={entity_id}, file_path={entity.file_path}")
        lock = self._get_entity_lock(entity_id)

        with lock:
            skip_id = self._should_skip_submission_locked(entity, "face_detection")
            if skip_id:
                logger.info(f"[TRACE] Skipping face_detection for entity_id={entity_id}, already has job={skip_id}")
                return skip_id

            try:
                if not entity.file_path:
                    logger.warning(f"Entity {entity_id} has no file_path")
                    return None

                file_path = self.storage_service.get_absolute_path(entity.file_path)
                if not file_path.exists():
                    logger.warning(f"File not found for entity {entity_id}: {file_path}")
                    return None

                logger.info(f"[TRACE] Submitting face_detection to compute for entity_id={entity_id}, file={file_path}")
                wrapped_callback, _ = make_once_only_callback(on_complete_callback)

                job_response = await self.compute_client.face_detection.detect(
                    image=file_path,
                    wait=False,
                    on_complete=wrapped_callback,
                )

                logger.info(f"[TRACE] face_detection job created: job_id={job_response.job_id} -> entity_id={entity_id}")
                self._register_job(entity, job_response.job_id, "face_detection")
                logger.info(f"[TRACE] Registered job mapping: job_id={job_response.job_id} -> entity_id={entity_id}")

                self.broadcast_entity_status(entity_id)

                # RACE CONDITION FIX: Check if job already completed (for very fast jobs)
                try:
                    await asyncio.sleep(0.05)
                    full_job = await self.compute_client.get_job(job_response.job_id)
                    if full_job and full_job.status in ("completed", "failed"):
                        await wrapped_callback(full_job)
                except Exception:
                    pass

                return job_response.job_id

            except Exception as e:
                logger.error(f"Failed to submit face_detection job for entity {entity_id}: {e}")
                self._register_failed_job(entity, "face_detection", str(e))
                return None

    @timed
    async def submit_hls_streaming(
        self,
        entity: EntitySchema | EntityVersionSchema,
        input_absolute_path: str,
        output_absolute_path: str,
        priority: int = 1,  # Default to high priority for HLS
        on_complete_callback: OnJobResponseCallback | None = None,
    ) -> str | None:
        """Submit HLS streaming manifest generation job using absolute paths.

        Thread-safe: Uses per-entity locks and atomic DB checks to prevent duplicate submissions.
        """
        entity_id = entity.id
        lock = self._get_entity_lock(entity_id)

        # 1. Acquire lock to serialize submission for this entity
        with lock:
            # 2. Re-check status inside the lock
            skip_id = self._should_skip_submission_locked(entity, "hls_streaming")
            if skip_id:
                return skip_id

            # 3. Proceed with submission if truly needed
            try:
                wrapped_callback = None
                if on_complete_callback:
                    wrapped_callback, _ = make_once_only_callback(on_complete_callback)

                async def on_progress(job: JobResponse):
                    self.update_job_progress(entity_id, job.job_id, job.progress)

                logger.info(f"Triggering new HLS streaming job for entity {entity_id}")
                job_response = await self.compute_client.hls_streaming.generate_manifest(
                    input_absolute_path=input_absolute_path,
                    output_absolute_path=output_absolute_path,
                    priority=priority,
                    wait=False,
                    on_progress=on_progress,
                    on_complete=wrapped_callback,
                )

                self._register_job(entity, job_response.job_id, "hls_streaming")
                logger.info(f"Submitted hls_streaming job {job_response.job_id} for entity {entity_id}")
                
                self.broadcast_entity_status(entity_id)
                return job_response.job_id

            except Exception as e:
                logger.error(f"Failed to submit hls_streaming job for entity {entity_id}: {e}")
                self._register_failed_job(entity, "hls_streaming", str(e))
                return None

    @timed
    async def submit_clip_embedding(
        self,
        entity: EntitySchema | EntityVersionSchema,
        on_complete_callback: OnJobResponseCallback,
    ) -> str | None:
        """Submit CLIP embedding job."""
        entity_id = entity.id
        lock = self._get_entity_lock(entity_id)

        with lock:
            skip_id = self._should_skip_submission_locked(entity, "clip_embedding")
            if skip_id:
                return skip_id

            try:
                if not entity.file_path:
                    return None
                file_path = self.storage_service.get_absolute_path(entity.file_path)

                wrapped_callback, _ = make_once_only_callback(on_complete_callback)

                job_response = await self.compute_client.clip_embedding.embed_image(
                    image=file_path,
                    wait=False,
                    on_complete=wrapped_callback,
                )

                self._register_job(entity, job_response.job_id, "clip_embedding")
                logger.info(f"Submitted clip_embedding job {job_response.job_id} for entity {entity_id}")

                self.broadcast_entity_status(entity_id)

                # RACE CONDITION FIX
                try:
                    await asyncio.sleep(0.05)
                    full_job = await self.compute_client.get_job(job_response.job_id)
                    if full_job and full_job.status in ("completed", "failed"):
                        await wrapped_callback(full_job)
                except Exception:
                    pass

                return job_response.job_id
            except Exception as e:
                logger.error(f"Failed to submit clip_embedding job for entity {entity_id}: {e}")
                self._register_failed_job(entity, "clip_embedding", str(e))
                return None

    @timed
    async def submit_dino_embedding(
        self,
        entity: EntitySchema | EntityVersionSchema,
        on_complete_callback: OnJobResponseCallback,
    ) -> str | None:
        """Submit DINOv2 embedding job."""
        entity_id = entity.id
        lock = self._get_entity_lock(entity_id)

        with lock:
            skip_id = self._should_skip_submission_locked(entity, "dino_embedding")
            if skip_id:
                return skip_id

            try:
                if not entity.file_path:
                    return None
                file_path = self.storage_service.get_absolute_path(entity.file_path)

                wrapped_callback, _ = make_once_only_callback(on_complete_callback)

                job_response = await self.compute_client.dino_embedding.embed_image(
                    image=file_path,
                    wait=False,
                    on_complete=wrapped_callback,
                )

                self._register_job(entity, job_response.job_id, "dino_embedding")
                logger.info(f"Submitted dino_embedding job {job_response.job_id} for entity {entity_id}")

                self.broadcast_entity_status(entity_id)

                # RACE CONDITION FIX
                try:
                    await asyncio.sleep(0.05)
                    full_job = await self.compute_client.get_job(job_response.job_id)
                    if full_job and full_job.status in ("completed", "failed"):
                        await wrapped_callback(full_job)
                except Exception:
                    pass

                return job_response.job_id
            except Exception as e:
                logger.error(f"Failed to submit dino_embedding job for entity {entity_id}: {e}")
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

    def reset_task_status(self, entity_id: int, task_type: str) -> None:
        """Reset the status of a specific task type to None.
        
        This is used when a job fails terminaly or when assets are manually removed (e.g. remove stream).
        """
        def reset(data: EntityIntelligenceData):
            if task_type == "face_embedding":
                data.inference_status.face_embeddings = []
            elif hasattr(data.inference_status, task_type):
                setattr(data.inference_status, task_type, None)
            
            data.last_updated = self._now_timestamp()
        
        self.db.intelligence.atomic_update_intelligence_data(entity_id, reset)
        self.broadcast_entity_status(entity_id)
