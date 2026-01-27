"""Job submission and management service for async compute tasks."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from store.broadcast_service.broadcaster import MInsightBroadcaster
    from store.broadcast_service.schemas import EntityStatusPayload

from datetime import UTC, datetime

from cl_client import ComputeClient
from cl_client.models import OnJobResponseCallback
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

    @staticmethod
    def _now_timestamp() -> int:
        """Get current timestamp in milliseconds.

        Returns:
            Current timestamp in milliseconds since epoch
        """
        return int(datetime.now(UTC).timestamp() * 1000)

    def update_job_status(self, entity_id: int, job_id: str, status: str, error_message: str | None = None) -> None:
        """Update job status in Entity.intelligence_data.

        Args:
            entity_id: Entity ID being processed
            job_id: Job ID to update
            status: New job status (e.g., "completed", "failed")
            error_message: Optional error message if job failed
        """
        try:
            entity = self.db.entity.get(entity_id)
            if not entity or not entity.intelligence_data:
                logger.warning(f"Entity {entity_id} not found or has no intelligence_data")
                return

            data = entity.intelligence_data
            
            # Find and update job in active_jobs
            for job in data.active_jobs:
                if job.job_id == job_id:
                    # Update status in inference_status
                    if job.task_type == "face_detection":
                        data.inference_status.face_detection = status
                    elif job.task_type == "clip_embedding":
                        data.inference_status.clip_embedding = status
                    elif job.task_type == "dino_embedding":
                        data.inference_status.dino_embedding = status
                    
                    # Remove from active_jobs if finished
                    if status in ("completed", "failed"):
                        data.active_jobs = [j for j in data.active_jobs if j.job_id != job_id]
                    break
            else:
                # Might be a face embedding job (if we track them differently or search list)
                # For now just use the task_type if known.
                pass
            
            if error_message:
                data.error_message = error_message
            
            data.last_updated = self._now_timestamp()
            
            # Re-calculate overall status
            inf = data.inference_status
            critical = [inf.face_detection, inf.clip_embedding, inf.dino_embedding]
            
            if any(s == "failed" for s in critical):
                data.overall_status = "failed"
            elif all(s == "completed" for s in critical):
                data.overall_status = "completed"
            elif all(s == "pending" for s in critical):
                data.overall_status = "queued"
            else:
                data.overall_status = "processing"

            _ = self.db.entity.update_intelligence_data(entity_id, data)
            logger.debug(f"Updated job {job_id} for entity {entity_id} to status {status}")
            self.broadcast_entity_status(entity_id)

        except Exception as e:
            logger.error(f"Failed to update job {job_id} status for entity {entity_id}: {e}")

    def delete_job_record(self, entity_id: int, job_id: str) -> None:
        """Remove job from active_jobs list."""
        try:
            entity = self.db.entity.get(entity_id)
            if entity and entity.intelligence_data:
                data = entity.intelligence_data
                data.active_jobs = [j for j in data.active_jobs if j.job_id != job_id]
                _ = self.db.entity.update_intelligence_data(entity_id, data)
        except Exception as e:
            logger.error(f"Failed to delete job record {job_id} for entity {entity_id}: {e}")

    def _register_job(self, entity: EntitySchema | EntityVersionSchema, job_id: str, task_type: str) -> None:
        """Helper to register an active job in the denormalized intelligence_data."""
        now = self._now_timestamp()
        db_entity = self.db.entity.get(entity.id)
        if not db_entity:
            return

        data = db_entity.intelligence_data or EntityIntelligenceData(last_updated=now)
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
            started_at=now
        ))
        data.last_updated = now
        _ = self.db.entity.update_intelligence_data(entity.id, data)

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

            job_response = await self.compute_client.face_detection.detect(
                image=file_path,
                wait=False,
                on_complete=on_complete_callback,
            )

            self._register_job(entity, job_response.job_id, "face_detection")
            logger.info(f"Submitted face_detection job {job_response.job_id} for entity {entity.id}")

            self.broadcast_entity_status(entity.id)
            return job_response.job_id

        except Exception as e:
            logger.error(f"Failed to submit face_detection job for entity {entity.id}: {e}")
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

            job_response = await self.compute_client.clip_embedding.embed_image(
                image=file_path,
                wait=False,
                on_complete=on_complete_callback,
            )

            self._register_job(entity, job_response.job_id, "clip_embedding")
            logger.info(f"Submitted clip_embedding job {job_response.job_id} for entity {entity.id}")

            self.broadcast_entity_status(entity.id)
            return job_response.job_id
        except Exception as e:
            logger.error(f"Failed to submit clip_embedding job for entity {entity.id}: {e}")
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

            job_response = await self.compute_client.dino_embedding.embed_image(
                image=file_path,
                wait=False,
                on_complete=on_complete_callback,
            )

            self._register_job(entity, job_response.job_id, "dino_embedding")
            logger.info(f"Submitted dino_embedding job {job_response.job_id} for entity {entity.id}")

            self.broadcast_entity_status(entity.id)
            return job_response.job_id
        except Exception as e:
            logger.error(f"Failed to submit dino_embedding job for entity {entity.id}: {e}")
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

            job_response = await self.compute_client.face_embedding.embed_faces(
                image=file_path,
                wait=False,
                on_complete=on_complete_callback,
            )

            self._register_job(entity, job_response.job_id, "face_embedding")
            logger.info(f"Submitted face_embedding job {job_response.job_id} for face {face.id}")

            self.broadcast_entity_status(entity.id)
            return job_response.job_id
        except Exception as e:
            logger.error(f"Failed to submit face_embedding job for face {face.id}: {e}")
            return None
