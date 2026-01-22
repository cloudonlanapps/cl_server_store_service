from __future__ import annotations

import logging
from sqlalchemy.orm import Session
from store.store.config import StoreConfig
from .logic.job_service import JobSubmissionService
from .logic.job_callbacks import JobCallbackHandler
from .logic.compute_singleton import get_compute_client
from .logic.pysdk_config import PySDKRuntimeConfig
from .logic.qdrant_singleton import get_qdrant_store
from .logic.dino_store_singleton import get_dino_store
from store.m_insight.models import EntityVersionData
from cl_client.models import JobResponse

logger = logging.getLogger(__name__)

class IntelligenceProcessingService:
    """Service layer for active intelligence/ML operations (job management).
    
    This service handles triggering ML jobs and coordinating callbacks.
    It requires full ML Compute/Auth credentials (PySDKRuntimeConfig).
    """

    def __init__(self, db: Session, config: StoreConfig, pysdk_config: PySDKRuntimeConfig):
        """Initialize the intelligence processing service."""
        self.db = db
        self.config = config
        self.pysdk_config = pysdk_config
        # We assume file_storage is needed if we are triggering jobs
        from store.store.entity_storage import EntityStorageService
        self.file_storage = EntityStorageService(str(config.media_storage_dir))
        
        # Initialize stores
        self.qdrant_store = get_qdrant_store(pysdk_config)
        self.dino_store = get_dino_store(pysdk_config)

    def _now_timestamp(self) -> int:
        """Return current UTC timestamp in milliseconds."""
        from datetime import UTC, datetime
        return int(datetime.now(UTC).timestamp() * 1000)

    async def trigger_async_jobs(self, entity: EntityVersionData) -> dict[str, str | None]:
        """Trigger face detection, CLIP, and DINO embedding jobs for an entity version."""
        # Get absolute file path
        if not entity.file_path:
            logger.warning(f"Entity {entity.id} has no file_path")
            return {"face_detection_job": None, "clip_embedding_job": None, "dino_embedding_job": None}

        absolute_path = self.file_storage.get_absolute_path(entity.file_path)
        if not absolute_path.exists():
            logger.warning(f"File not found for entity {entity.id}: {absolute_path}")
            return {"face_detection_job": None, "clip_embedding_job": None, "dino_embedding_job": None}

        compute_client = get_compute_client()

        # Create handlers with job_service and config
        job_service = JobSubmissionService(compute_client)
        callback_handler = JobCallbackHandler(
            compute_client,
            self.qdrant_store,
            self.dino_store,
            config=self.config,
            pysdk_config=self.pysdk_config,
            job_submission_service=job_service,
        )

        async def face_detection_callback(job: JobResponse) -> None:
            """Handle face detection job completion."""
            job_service.update_job_status(job.job_id, job.status, job.error_message)
            if job.status == "completed":
                await callback_handler.handle_face_detection_complete(entity.id, job)

        async def clip_embedding_callback(job: JobResponse) -> None:
            """Handle CLIP embedding job completion."""
            job_service.update_job_status(job.job_id, job.status, job.error_message)
            if job.status == "completed":
                await callback_handler.handle_clip_embedding_complete(entity.id, job)

        async def dino_embedding_callback(job: JobResponse) -> None:
            """Handle DINO embedding job completion."""
            job_service.update_job_status(job.job_id, job.status, job.error_message)
            if job.status == "completed":
                await callback_handler.handle_dino_embedding_complete(entity.id, job)

        # Submit jobs
        face_job_id = await job_service.submit_face_detection(
            entity_id=entity.id,
            file_path=str(absolute_path),
            on_complete_callback=face_detection_callback,
        )

        clip_job_id = await job_service.submit_clip_embedding(
            entity_id=entity.id,
            file_path=str(absolute_path),
            on_complete_callback=clip_embedding_callback,
        )

        dino_job_id = await job_service.submit_dino_embedding(
            entity_id=entity.id,
            file_path=str(absolute_path),
            on_complete_callback=dino_embedding_callback,
        )

        logger.info(
            f"Submitted jobs for entity {entity.id}: "
            + f"face_detection={face_job_id}, clip_embedding={clip_job_id}"
        )

        return {
            "face_detection_job": face_job_id,
            "clip_embedding_job": clip_job_id,
            "dino_embedding_job": dino_job_id,
        }
