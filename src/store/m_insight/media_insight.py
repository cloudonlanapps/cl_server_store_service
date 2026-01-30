from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import configure_mappers
from store.db_service import DBService, EntityIntelligenceData
from sqlalchemy_continuum import version_class  # pyright: ignore[reportAttributeAccessIssue]
from store.db_service.db_internals import (
    Entity,
    EntityIntelligence,
    EntitySyncState,
    database,
)
from store.common.storage import StorageService
from .config import MInsightConfig
from .job_callbacks import JobCallbackHandler
from .job_service import JobSubmissionService
from .schemas import EntityVersionSchema
from store.vectorstore_services.vector_stores import get_clip_store, get_dino_store, get_face_store
from cl_ml_tools.utils.profiling import timed

if TYPE_CHECKING:
    from cl_client import ComputeClient, SessionManager
    from cl_client.models import JobResponse

    from store.broadcast_service.broadcaster import MInsightBroadcaster


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
        self.db: DBService = DBService()
        self._initialized: bool = False

        # Verify database is initialized
        database.init_db()

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
                broadcaster=self.broadcaster,
                db=self.db
            )

            self.callback_handler = JobCallbackHandler(
                self.compute_client,
                clip_store,
                dino_store,
                face_store,
                config=self.config,
                db=self.db,
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
    async def process(self, data: EntityVersionSchema) -> bool:
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

    def _is_qualified(self, entity_version: EntityVersionSchema) -> bool:
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
        database.init_db()

        session = database.SessionLocal()
        try:
            # Direct query to intelligence table
            intel = session.query(EntityIntelligence).filter(EntityIntelligence.entity_id == entity_version.id).first()
            
            if not intel or not intel.intelligence_data:
                # New image or no intelligence data yet
                return True

            # Check if active_processing_md5 changed
            try:
                # intel.intelligence_data is already a dict (JSON type)
                raw_data = cast(dict[str, object], intel.intelligence_data)
                intel_obj = EntityIntelligenceData.model_validate(raw_data)
                active_md5 = intel_obj.active_processing_md5
                return active_md5 != entity_version.md5
            except Exception:
                return True
        finally:
            session.close()

    @timed
    async def _enqueue_image(self, entity_version: EntityVersionSchema) -> None:
        """Enqueue a qualified image for processing and trigger async jobs.
        
        Args:
            entity_version: Entity version data from Pydantic model
        """
        entity_id = entity_version.id
        try:
            await self._trigger_async_jobs(entity_version)
            logger.info(f"Image intelligence jobs triggered for {entity_id}")
        except Exception as e:
            logger.error(f"Failed to trigger jobs for image {entity_id}: {e}")

    @timed
    async def _trigger_async_jobs(self, entity_version: EntityVersionSchema) -> None:
        """Trigger face detection, CLIP, and DINO embedding jobs.
        """
        if not self._initialized or not self.job_service or not self.callback_handler:
            await self.initialize()
            if not self.job_service or not self.callback_handler:
                return

        # Fetch SQLAlchemy Entity
        entity = self.db.entity.get(entity_version.id)
        if not entity:
            logger.error(f"Entity {entity_version.id} not found for job trigger")
            return

        # Define callbacks
        async def face_detection_callback(job: JobResponse) -> None:
            if job.status == "completed" and self.callback_handler:
                await self.callback_handler.handle_face_detection_complete(entity.id, job)
            if self.job_service:
                self.job_service.update_job_status(entity.id, job.job_id, job.status, job.error_message)

        async def clip_embedding_callback(job: JobResponse) -> None:
            if job.status == "completed" and self.callback_handler:
                await self.callback_handler.handle_clip_embedding_complete(entity.id, job)
            if self.job_service:
                self.job_service.update_job_status(entity.id, job.job_id, job.status, job.error_message)

        async def dino_embedding_callback(job: JobResponse) -> None:
            if job.status == "completed" and self.callback_handler:
                await self.callback_handler.handle_dino_embedding_complete(entity.id, job)
            if self.job_service:
                self.job_service.update_job_status(entity.id, job.job_id, job.status, job.error_message)

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

        # Trigger initial status update
        self.job_service.broadcast_entity_status(entity.id)

    def _get_last_version(self) -> int:
        """Get last processed version from sync state."""
        database.init_db()

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
        database.init_db()

        session = database.SessionLocal()
        try:
            stmt = select(EntitySyncState).where(EntitySyncState.id == 1)
            sync_state = session.execute(stmt).scalar_one()
            sync_state.last_version = version
            session.commit()
        finally:
            session.close()

    def _get_entity_deltas(self, last_version: int) -> dict[int, EntityVersionSchema]:
        """Get entity changes since last version, coalesced by entity ID."""
        database.init_db()

        session = database.SessionLocal()
        try:
            stmt = (
                select(self.EntityVersion)
                .where(self.EntityVersion.transaction_id > last_version)  # pyright: ignore[reportAny]
                .order_by(self.EntityVersion.transaction_id)  # pyright: ignore[reportAny]
            )
            versions = session.execute(stmt).scalars().all()

            entity_map: dict[int, EntityVersionSchema] = {}
            for version in versions:  # pyright: ignore[reportAny]
                entity_map[version.id] = EntityVersionSchema.model_validate(version)  # pyright: ignore[reportAny]

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
