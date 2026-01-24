"""Job submission and management service for async compute tasks."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .broadcaster import MInsightBroadcaster
    from .schemas import EntityStatusPayload

from datetime import UTC, datetime

from cl_client import ComputeClient
from cl_client.models import OnJobResponseCallback
from cl_ml_tools.utils.profiling import timed
from loguru import logger

from store.common.storage import StorageService
from store.db_service import (
    DBService,
    EntityJobSchema,
    EntitySchema,
    EntityVersionSchema,
    FaceSchema,
)

from .schemas import EntityStatusDetails, EntityStatusPayload


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
        broadcaster: "MInsightBroadcaster | None" = None
    ) -> None:
        """Initialize job submission service.

        Args:
            compute_client: ComputeClient instance for job submission
            storage_service: StorageService for file path resolution
            broadcaster: Optional broadcaster for status updates
        """
        self.compute_client = compute_client
        self.storage_service = storage_service
        self.broadcaster = broadcaster
        self.db = DBService()

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
        try:
            completed_at = self._now_timestamp() if status in ("completed", "failed") else None
            result, entity_id = self.db.job.update_status(
                job_id=job_id,
                status=status,
                error_message=error_message,
                completed_at=completed_at
            )
            
            if result and entity_id:
                logger.debug(f"Updated job {job_id} status to {status}")
                self.broadcast_entity_status(entity_id)
            else:
                logger.warning(f"Job {job_id} not found or failed to update")

        except Exception as e:
            logger.error(f"Failed to update job {job_id} status: {e}")

    def delete_job_record(self, job_id: str) -> None:
        """Delete job record from entity_jobs table.

        Args:
            job_id: Job ID to delete
        """
        try:
            deleted = self.db.job.delete_by_job_id(job_id)
            if deleted:
                logger.debug(f"Deleted job record {job_id}")
            else:
                logger.warning(f"Job {job_id} not found for deletion")
        except Exception as e:
            logger.error(f"Failed to delete job record {job_id}: {e}")

    @timed
    def _get_entity_status(self, entity_id: int) -> "EntityStatusPayload | None":
        """Calculate aggregate status for an entity.

        Args:
            entity_id: Entity ID

        Returns:
            EntityStatusPayload or None if entity not found
        """
        # 1. Get Intelligence Record
        intelligence = self.db.intelligence.get_by_entity_id(entity_id)
        if not intelligence:
            return None

        # 2. Get All Jobs for this entity
        jobs = self.db.job.get_by_entity_id(entity_id)
        job_map = {job.job_id: job for job in jobs}

        # Helper to get job status
        def get_job_status(job_id: str | None) -> str:
            if not job_id:
                return "pending"
            job = job_map.get(job_id)
            if not job:
                return "pending"
            return job.status

        # 3. Build Details
        details = EntityStatusDetails()

        # Face Detection
        fd_status = get_job_status(intelligence.face_detection_job_id)
        fd_count = None
        if fd_status == "completed":
            fd_count = self.db.face.count_by_entity_id(entity_id)
            logger.debug(f"Entity {entity_id} status calculation: face_detection=completed, found {fd_count} faces in DB")
        
        details.face_detection = fd_status
        details.face_count = fd_count

        # Embeddings
        details.clip_embedding = get_job_status(intelligence.clip_job_id)
        details.dino_embedding = get_job_status(intelligence.dino_job_id)

        # Face Embeddings
        face_agg_status = "completed" # Default if no faces
        
        if fd_status == "completed":
            actual_faces = fd_count or 0
            if actual_faces > 0:
                job_ids = intelligence.face_embedding_job_ids or []
                statuses = []
                all_faces_done = True
                has_failure = False
                
                for i in range(actual_faces):
                    if i < len(job_ids):
                        s = get_job_status(job_ids[i])
                    else:
                        s = "pending"
                    
                    statuses.append(s)
                    
                    if s == "failed":
                        has_failure = True
                    if s != "completed":
                        all_faces_done = False
                
                details.face_embeddings = statuses
                
                if has_failure:
                    face_agg_status = "failed"
                elif not all_faces_done:
                    face_agg_status = "processing"
            else:
                details.face_embeddings = [] # 0 faces
                
        elif fd_status == "failed":
            face_agg_status = "skipped"
            details.face_embeddings = None
        else:
            face_agg_status = "pending"
            details.face_embeddings = None

        # 4. Aggregate Overall Status
        critical_statuses = [
            details.face_detection,
            details.clip_embedding,
            details.dino_embedding
        ]
        
        if any(s == "failed" for s in critical_statuses) or face_agg_status == "failed":
            overall = "failed"
        elif all(s == "completed" for s in critical_statuses) and face_agg_status == "completed":
            overall = "completed"
        elif all(s == "pending" for s in critical_statuses) and face_agg_status == "pending":
             overall = "queued"
        else:
            overall = "processing"

        return EntityStatusPayload(
            entity_id=entity_id,
            status=overall,
            details=details,
            timestamp=self._now_timestamp()
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

            now = self._now_timestamp()
            job_data = EntityJobSchema(
                entity_id=entity.id,
                job_id=job_response.job_id,
                task_type="face_detection",
                status="queued",
                created_at=now,
                updated_at=now,
            )
            self.db.job.create(job_data)
            logger.info(
                f"Submitted face_detection job {job_response.job_id} for entity {entity.id}"
            )

            # Broadcast update
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

            now = self._now_timestamp()
            job_data = EntityJobSchema(
                entity_id=entity.id,
                job_id=job_response.job_id,
                task_type="clip_embedding",
                status="queued",
                created_at=now,
                updated_at=now,
            )
            self.db.job.create(job_data)
            logger.info(
                f"Submitted clip_embedding job {job_response.job_id} for entity {entity.id}"
            )

            # Broadcast update
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

            now = self._now_timestamp()
            job_data = EntityJobSchema(
                entity_id=entity.id,
                job_id=job_response.job_id,
                task_type="dino_embedding",
                status="queued",
                created_at=now,
                updated_at=now,
            )
            self.db.job.create(job_data)
            logger.info(
                f"Submitted dino_embedding job {job_response.job_id} for entity {entity.id}"
            )

            # Broadcast update
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

            now = self._now_timestamp()
            # Track face_embedding jobs under the parent entity
            job_data = EntityJobSchema(
                entity_id=entity.id,
                job_id=job_response.job_id,
                task_type="face_embedding",
                status="queued",
                created_at=now,
                updated_at=now,
            )
            self.db.job.create(job_data)
            logger.info(
                f"Submitted face_embedding job {job_response.job_id} "
                + f"for face {face.id} (entity {entity.id})"
            )

            # Broadcast update
            self.broadcast_entity_status(entity.id)
            return job_response.job_id
        except Exception as e:
            logger.error(f"Failed to submit face_embedding job for face {face.id}: {e}")
            return None
