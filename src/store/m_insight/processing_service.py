from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from cl_client.models import JobResponse
from store.store.config import StoreConfig

from cl_client import ComputeClient, ServerConfig, SessionManager
from store.store.config import StoreConfig

from .config import MInsightConfig
from .job_callbacks import JobCallbackHandler
from .job_service import JobSubmissionService
from .models import EntityVersionData
from .vector_stores import get_clip_store, get_dino_store

logger = logging.getLogger(__name__)


class IntelligenceProcessingService:
    """Service layer for active intelligence/ML operations (job management).

    This service handles triggering ML jobs and coordinating callbacks.
    """

    _compute_client: ComputeClient | None = None
    _compute_session: SessionManager | None = None
    _job_service: JobSubmissionService | None = None
    _callback_handler: JobCallbackHandler | None = None

    def __init__(self, db: Session, store_config: StoreConfig, minsight_config: MInsightConfig):
        """Initialize the intelligence processing service."""
        self.db = db
        self.store_config = store_config
        self.minsight_config = minsight_config

        # We assume file_storage is needed if we are triggering jobs
        from store.store.entity_storage import EntityStorageService

        self.file_storage = EntityStorageService(str(store_config.media_storage_dir))

    @classmethod
    async def _ensure_singletons(
        cls, store_config: StoreConfig, minsight_config: MInsightConfig
    ) -> tuple[ComputeClient, JobSubmissionService, JobCallbackHandler]:
        """Ensure all shared singletons are initialized."""
        if cls._compute_client is None:
            # 1. Initialize Compute Client & Session
            server_config = ServerConfig(
                auth_url=minsight_config.auth_service_url,
                compute_url=minsight_config.compute_service_url,
                mqtt_broker=minsight_config.mqtt_broker,
                mqtt_port=minsight_config.mqtt_port,
            )

            cls._compute_session = SessionManager(server_config=server_config)
            await cls._compute_session.login(
                username=minsight_config.compute_username,
                password=minsight_config.compute_password,
            )
            cls._compute_client = cls._compute_session.create_compute_client()

            # 2. Initialize Vector Stores
            clip_store = get_clip_store(
                url=store_config.qdrant_url,
                collection_name=store_config.qdrant_collections.clip_embedding_collection_name,
            )
            dino_store = get_dino_store(
                url=store_config.qdrant_url,
                collection_name=store_config.qdrant_collections.dino_embedding_collection_name,
            )

            # 3. Initialize Shared Services
            cls._job_service = JobSubmissionService(cls._compute_client)
            cls._callback_handler = JobCallbackHandler(
                cls._compute_client,
                clip_store,
                dino_store,
                config=store_config,
                minsight_config=minsight_config,
                job_submission_service=cls._job_service,
            )

            logger.info(
                f"Initialized IntelligenceProcessingService singletons: "
                f"compute={minsight_config.compute_service_url}, "
                f"user={minsight_config.compute_username}"
            )

        if cls._job_service is None or cls._callback_handler is None:
            raise RuntimeError("Failed to initialize singletons")

        return cls._compute_client, cls._job_service, cls._callback_handler

    @classmethod
    async def shutdown(cls) -> None:
        """Shutdown shared singletons."""
        if cls._compute_client:
            await cls._compute_client.close()
            cls._compute_client = None

        if cls._compute_session:
            await cls._compute_session.close()
            cls._compute_session = None

        cls._job_service = None
        cls._callback_handler = None
        logger.info("IntelligenceProcessingService shutdown complete")

    def _now_timestamp(self) -> int:
        """Return current UTC timestamp in milliseconds."""
        from datetime import UTC, datetime

        return int(datetime.now(UTC).timestamp() * 1000)

    async def trigger_async_jobs(self, entity: EntityVersionData) -> dict[str, str | None]:
        """Trigger face detection, CLIP, and DINO embedding jobs for an entity version."""
        # Get absolute file path
        if not entity.file_path:
            logger.warning(f"Entity {entity.id} has no file_path")
            return {
                "face_detection_job": None,
                "clip_embedding_job": None,
                "dino_embedding_job": None,
            }

        absolute_path = self.file_storage.get_absolute_path(entity.file_path)
        if not absolute_path.exists():
            logger.warning(f"File not found for entity {entity.id}: {absolute_path}")
            return {
                "face_detection_job": None,
                "clip_embedding_job": None,
                "dino_embedding_job": None,
            }

        # Ensure singletons initialized
        _, job_service, callback_handler = await self._ensure_singletons(
            self.store_config, self.minsight_config
        )

        async def face_detection_callback(job: JobResponse) -> None:
            """Handle face detection job completion."""
            if job.status == "completed":
                await callback_handler.handle_face_detection_complete(entity.id, job)
            job_service.update_job_status(job.job_id, job.status, job.error_message)

        async def clip_embedding_callback(job: JobResponse) -> None:
            """Handle CLIP embedding job completion."""
            if job.status == "completed":
                await callback_handler.handle_clip_embedding_complete(entity.id, job)
            job_service.update_job_status(job.job_id, job.status, job.error_message)

        async def dino_embedding_callback(job: JobResponse) -> None:
            """Handle DINO embedding job completion."""
            if job.status == "completed":
                await callback_handler.handle_dino_embedding_complete(entity.id, job)
            job_service.update_job_status(job.job_id, job.status, job.error_message)

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
            f"face_detection={face_job_id}, clip_embedding={clip_job_id}, dino_embedding={dino_job_id}"
        )

        return {
            "face_detection_job": face_job_id,
            "clip_embedding_job": clip_job_id,
            "dino_embedding_job": dino_job_id,
        }
