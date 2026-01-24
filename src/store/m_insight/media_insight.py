from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import configure_mappers
from sqlalchemy_continuum import (
    version_class,  # pyright: ignore[reportAttributeAccessIssue, reportUnknownVariableType]
)

from store.common import StorageService, database

from ..common.models import Entity, EntitySyncState, ImageIntelligence
from .config import MInsightConfig
from .job_callbacks import JobCallbackHandler
from .job_service import JobSubmissionService
from .schemas import EntityVersionData
from .vector_stores import get_clip_store, get_dino_store, get_face_store
from cl_ml_tools.utils.profiling import timed

if TYPE_CHECKING:
    from cl_client import ComputeClient, SessionManager
    from cl_client.models import JobResponse

    from .broadcaster import MInsightBroadcaster


class MediaInsight:
    """Processor that handles image intelligence."""

    def __init__(self, config: MInsightConfig, broadcaster: MInsightBroadcaster):
        """Initialize m_insight processor.

        Args:
            config: Processor configuration
            broadcaster: Optional MInsightBroadcaster for event publishing
        """
        self.config: MInsightConfig = config
        self.broadcaster: MInsightBroadcaster = broadcaster

        # Resources initialized in initialize()
        self.compute_client: ComputeClient | None = None
        self.compute_session: SessionManager | None = None
        self.storage_service: StorageService | None = None
        self.job_service: JobSubmissionService | None = None
        self.callback_handler: JobCallbackHandler | None = None
        self._initialized: bool = False

        # Verify database is initialized
        if not database.SessionLocal:
            raise RuntimeError("Database not initialized. Call database.init_db() first.")

        # Get Entity version class
        configure_mappers()
        self.EntityVersion: type[Any] = version_class(Entity)  # pyright: ignore[reportExplicitAny]

        logger.info(f"mInsight processor initialized (id: {config.id})")

    async def initialize(self) -> None:
        """Initialize external services (Compute, Storage, Vector Stores)."""
        if self._initialized:
            return

        try:
            from cl_client import ServerConfig, SessionManager

            # Initialize Storage Service
            self.storage_service = StorageService(str(self.config.media_storage_dir))

            # Initialize Compute Client & Session
            if self.config.mqtt_port:
                server_config = ServerConfig(
                    auth_url=self.config.auth_service_url,
                    compute_url=self.config.compute_service_url,
                    mqtt_broker=self.config.mqtt_broker,
                    mqtt_port=self.config.mqtt_port,
                )
            else:
                raise Exception("MQTT port is required")

            self.compute_session = SessionManager(server_config=server_config)
            _ = await self.compute_session.login(
                username=self.config.compute_username,
                password=self.config.compute_password,
            )
            self.compute_client = self.compute_session.create_compute_client()

            # Initialize Vector Stores
            clip_store = get_clip_store(
                url=self.config.qdrant_url,
                collection_name=self.config.qdrant_collection,
                vector_size=512,  # Default for CLIP
            )
            dino_store = get_dino_store(
                url=self.config.qdrant_url,
                collection_name=self.config.dino_collection,
                vector_size=384,  # Default for DINOv2-S
            )
            face_store = get_face_store(
                url=self.config.qdrant_url,
                collection_name=self.config.face_collection,
                vector_size=self.config.face_vector_size,
            )

            # Initialize Services
            self.job_service = JobSubmissionService(
                self.compute_client, 
                self.storage_service,
                broadcaster=self.broadcaster
            )

            self.callback_handler = JobCallbackHandler(
                self.compute_client,
                clip_store,
                dino_store,
                face_store,
                config=self.config,
                job_submission_service=self.job_service,
            )

            self._initialized = True
            logger.info("MInsightProcessor services initialized")

        except Exception as e:
            logger.error(f"Failed to initialize MInsightProcessor services: {e}")
            raise

    async def shutdown(self) -> None:
        """Shutdown resources."""
        if self.compute_client:
            await self.compute_client.close()
        if self.compute_session:
            await self.compute_session.close()
        self._initialized = False
        logger.info("MInsightProcessor services shut down")

    @timed
    async def process(self, data: EntityVersionData) -> bool:
        """Process an entity version for intelligence extraction.

        This method:
        1. Checks if the entity qualifies for processing (type=image, not deleted, md5 changed)
        2. If qualified, upserts to image_intelligence and triggers processing
        3. Returns True if processed, False if not qualified

        Args:
            data: Entity version data from Pydantic model

        Returns:
            True if image was processed, False if not qualified
        """
        # Step 1: Check qualification (atomic read)
        if not self._is_qualified(data):
            return False

        # Step 2: Enqueue for processing (atomic write)
        await self._enqueue_image(data)
        return True

    def _is_qualified(self, entity_version: EntityVersionData) -> bool:
        """Check if entity qualifies for processing.

        Uses atomic database read - opens session, reads, closes immediately.

        Args:
            entity_version: Entity version data from Pydantic model

        Returns:
            True if entity should be processed
        """
        # Must be image type
        if entity_version.type != "image":
            return False

        # Must not be deleted (soft delete creates version with is_deleted=True)
        if entity_version.is_deleted:
            return False

        # Must have md5
        if not entity_version.md5:
            return False

        # Atomic read: Check if md5 changed from existing intelligence record
        if not database.SessionLocal:
            raise RuntimeError("Database not initialized")

        session = database.SessionLocal()
        try:
            stmt = select(ImageIntelligence).where(ImageIntelligence.entity_id == entity_version.id)
            existing = session.execute(stmt).scalar_one_or_none()

            if existing is None:
                # New image
                return True

            # Check if md5 changed
            return existing.md5 != entity_version.md5
        finally:
            session.close()

    @timed
    async def _enqueue_image(self, entity_version: EntityVersionData) -> None:
        """Enqueue a qualified image for processing.

        Uses atomic database write - opens session, upserts, commits, closes.
        Derives image_path from entity file_path and config.
        Triggers async jobs.

        Args:
            entity_version: Entity version data from Pydantic model
        """
        entity_id = entity_version.id
        md5 = entity_version.md5
        file_path = entity_version.file_path
        transaction_id = entity_version.transaction_id

        if not isinstance(md5, str):
            logger.warning(f"Invalid md5 for image {entity_id}: {md5}")
            return

        if not file_path:
            logger.warning(f"No file_path for image {entity_id}")
            return

        # Derive absolute image path from relative file_path and config
        image_path = str(self.config.media_storage_dir / file_path)

        version_val = transaction_id if transaction_id is not None else 0

        # Atomic write: Upsert intelligence record
        if not database.SessionLocal:
            raise RuntimeError("Database not initialized")

        session = database.SessionLocal()
        try:
            stmt = select(ImageIntelligence).where(ImageIntelligence.entity_id == entity_id)
            intelligence = session.execute(stmt).scalar_one_or_none()

            if intelligence is None:
                intelligence = ImageIntelligence(
                    entity_id=entity_id,
                    md5=md5,
                    status="queued",
                    image_path=image_path,
                    version=version_val,
                )
                session.add(intelligence)
            else:
                intelligence.md5 = md5
                intelligence.status = "queued"
                intelligence.image_path = image_path
                intelligence.version = version_val

            session.commit()
            logger.info(f"Image intelligence record created/updated for {entity_id}")

        except Exception as e:
            logger.error(f"Failed to enqueue image {entity_id} for intelligence: {e}")
            session.rollback()
            return
        finally:
            session.close()

        # Trigger async jobs AFTER closing the enqueue session to reduce lock duration
        try:
            await self._trigger_async_jobs(entity_version)
            logger.info(f"Image intelligence jobs triggered for {entity_id}")
        except Exception as e:
            logger.error(f"Failed to trigger jobs for image {entity_id}: {e}")

    @timed
    async def _trigger_async_jobs(self, entity: EntityVersionData) -> None:
        """Trigger face detection, CLIP, and DINO embedding jobs for an entity version.

        Args:
            entity: Entity version data
        """
        if not self._initialized or not self.job_service or not self.callback_handler:
            logger.warning("Services not initialized, attempting initialization")
            await self.initialize()

        # Get absolute file path
        # EntityVersionData doesn't have get_file_path unless we added it?
        # Yes, we added it in Step 309 context summary (view_file of schemas.py might trigger if I checked it).
        # But here I need storage_service.

        # Manually resolving path if needed, or using entity helper if available
        # logic from processing_service:
        # absolute_path = entity.get_file_path(self.storage_service)

        # Let's verify EntityVersionData has get_file_path and it takes storage_service
        # Assuming it does based on prev edits.

        try:
            if not self.storage_service:  # Should be init by now
                raise RuntimeError("Storage service not initialized")

            absolute_path = entity.get_file_path(self.storage_service)
        except (AttributeError, ValueError):
            # Fallback if method missing or file_path missing
            absolute_path = (
                self.config.media_storage_dir / entity.file_path if entity.file_path else None
            )

        if not absolute_path or not absolute_path.exists():
            logger.warning(f"File not found for entity {entity.id}: {absolute_path}")
            return

        # Define callbacks
        # We need to capture variables safely.

        # We need 'self' to access callback_handler

        async def face_detection_callback(job: JobResponse) -> None:
            if job.status == "completed" and self.callback_handler:
                await self.callback_handler.handle_face_detection_complete(entity.id, job)
            if self.job_service:
                self.job_service.update_job_status(job.job_id, job.status, job.error_message)

        async def clip_embedding_callback(job: JobResponse) -> None:
            if job.status == "completed" and self.callback_handler:
                await self.callback_handler.handle_clip_embedding_complete(entity.id, job)
            if self.job_service:
                self.job_service.update_job_status(job.job_id, job.status, job.error_message)

        async def dino_embedding_callback(job: JobResponse) -> None:
            if job.status == "completed" and self.callback_handler:
                await self.callback_handler.handle_dino_embedding_complete(entity.id, job)
            if self.job_service:
                self.job_service.update_job_status(job.job_id, job.status, job.error_message)

        if not self.job_service:
            logger.error("Job service not available")
            return

        # Submit jobs
        face_job_id = await self.job_service.submit_face_detection(
            entity=entity,
            on_complete_callback=face_detection_callback,
        )

        clip_job_id = await self.job_service.submit_clip_embedding(
            entity=entity,
            on_complete_callback=clip_embedding_callback,
        )

        dino_job_id = await self.job_service.submit_dino_embedding(
            entity=entity,
            on_complete_callback=dino_embedding_callback,
        )

        logger.info(
            f"Submitted jobs for entity {entity.id}: "
            + f"face_detection={face_job_id}, clip_embedding={clip_job_id}, dino_embedding={dino_job_id}"
        )

        # Update ImageIntelligence with job IDs
        if not database.SessionLocal:
            raise RuntimeError("Database not initialized")

        session = database.SessionLocal()
        try:
            # Re-query using primary key (entity_id)
            intelligence = (
                session.query(ImageIntelligence)
                .filter(ImageIntelligence.entity_id == entity.id)
                .first()
            )
            if intelligence:
                intelligence.face_detection_job_id = face_job_id
                intelligence.clip_job_id = clip_job_id
                intelligence.dino_job_id = dino_job_id
                intelligence.processing_status = "processing"
                session.commit()
        except Exception as e:
            logger.error(f"Failed to update ImageIntelligence job IDs for {entity.id}: {e}")
            session.rollback()
        finally:
            session.close()

        # Trigger initial status update
        if self.job_service:
            self.job_service.broadcast_entity_status(entity.id)

    def _get_last_version(self) -> int:
        """Get last processed version from sync state."""
        if not database.SessionLocal:
            raise RuntimeError("Database not initialized")

        session = database.SessionLocal()
        try:
            stmt = select(EntitySyncState).where(EntitySyncState.id == 1)
            sync_state = session.execute(stmt).scalar_one_or_none()

            if sync_state is None:
                sync_state = EntitySyncState(id=1, last_version=0)
                session.add(sync_state)
                session.commit()
                return 0

            return sync_state.last_version
        finally:
            session.close()

    def _update_last_version(self, version: int) -> None:
        """Update last processed version in sync state."""
        if not database.SessionLocal:
            raise RuntimeError("Database not initialized")

        session = database.SessionLocal()
        try:
            stmt = select(EntitySyncState).where(EntitySyncState.id == 1)
            sync_state = session.execute(stmt).scalar_one()
            sync_state.last_version = version
            session.commit()
        finally:
            session.close()

    def _get_entity_deltas(self, last_version: int) -> dict[int, EntityVersionData]:
        """Get entity changes since last version, coalesced by entity ID."""
        if not database.SessionLocal:
            raise RuntimeError("Database not initialized")

        session = database.SessionLocal()
        try:
            stmt = (
                select(self.EntityVersion)
                .where(self.EntityVersion.transaction_id > last_version)  # pyright: ignore[reportAny]
                .order_by(self.EntityVersion.transaction_id)  # pyright: ignore[reportAny]
            )
            versions = session.execute(stmt).scalars().all()

            entity_map: dict[int, EntityVersionData] = {}
            for version in versions:  # pyright: ignore[reportAny]
                entity_map[version.id] = EntityVersionData.model_validate(version)  # pyright: ignore[reportAny]

            return entity_map
        finally:
            session.close()

    async def run_once(self) -> int:
        """Perform one reconciliation cycle of entity changes."""

        # Ensure services are initialized
        if not self._initialized:
            await self.initialize()

        # Atomic read: Get last processed version
        last_version = self._get_last_version()
        logger.info(f"Starting reconciliation from version {last_version}")

        # Atomic read: Get entity deltas
        entity_deltas = self._get_entity_deltas(last_version)

        if not entity_deltas:
            logger.debug("No new entity changes")
            return 0

        # Find max transaction_id
        max_transaction_id = max(
            (
                version.transaction_id
                for version in entity_deltas.values()
                if version.transaction_id is not None
            ),
            default=last_version,
        )

        if self.broadcaster:
            self.broadcaster.publish_start(
                version_start=last_version, version_end=max_transaction_id
            )

        # Process each image
        processed_count = 0
        for entity_version in entity_deltas.values():
            if await self.process(entity_version):
                processed_count += 1

        # Atomic write: Update last version
        self._update_last_version(max_transaction_id)
        logger.debug(f"Advanced version to {max_transaction_id}")

        if self.broadcaster:
            self.broadcaster.publish_end(processed_count=processed_count)

        logger.info(f"Reconciliation complete: processed {processed_count} images")
        return processed_count
