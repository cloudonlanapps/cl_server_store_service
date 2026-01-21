from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session, configure_mappers
from sqlalchemy_continuum import version_class  # pyright: ignore[reportAttributeAccessIssue]

from store.common import database
from ..common.models import Entity
from .models import EntitySyncState, EntityVersionData, ImageIntelligence
from .config import MInsightConfig
from .intelligence.service import MInsightEmbeddingService

if TYPE_CHECKING:
    from .broadcaster import MInsightBroadcaster


class mInsight:
    """Processor that handles image intelligence."""

    def __init__(self, config: MInsightConfig, broadcaster: MInsightBroadcaster | None = None):
        """Initialize m_insight processor.

        Args:
            config: Processor configuration
            broadcaster: Optional MInsightBroadcaster for event publishing
        """
        self.config: MInsightConfig = config
        self.broadcaster = broadcaster

        # Verify database is initialized
        if not database.SessionLocal:
            raise RuntimeError("Database not initialized. Call database.init_db() first.")

        # Get Entity version class
        configure_mappers()
        self.EntityVersion: type[Any] = version_class(Entity)

        logger.info(f"mInsight processor initialized (id: {config.id})")

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
            stmt = select(ImageIntelligence).where(
                ImageIntelligence.image_id == entity_version.id
            )
            existing = session.execute(stmt).scalar_one_or_none()

            if existing is None:
                # New image
                return True

            # Check if md5 changed
            return existing.md5 != entity_version.md5
        finally:
            session.close()

    async def _enqueue_image(self, entity_version: EntityVersionData) -> None:
        """Enqueue a qualified image for processing.

        Uses atomic database write - opens session, upserts, commits, closes.
        Derives image_path from entity file_path and config.
        Triggers async jobs using MInsightEmbeddingService.

        Args:
            entity_version: Entity version data from Pydantic model
        """
        entity_id = entity_version.id
        md5 = entity_version.md5
        file_path = entity_version.file_path
        transaction_id = entity_version.transaction_id

        if not isinstance(entity_id, int) or not isinstance(md5, str):
            logger.warning(f"Invalid entity version: id={entity_id}, md5={md5}")
            return

        if not file_path:
            logger.warning(f"No file_path for image {entity_id}")
            return

        # Derive absolute image path from relative file_path and config
        image_path = str(self.config.media_storage_dir / file_path)

        # Atomic write: Upsert intelligence record
        if not database.SessionLocal:
            raise RuntimeError("Database not initialized")

        session = database.SessionLocal()
        try:
            stmt = select(ImageIntelligence).where(ImageIntelligence.image_id == entity_id)
            intelligence = session.execute(stmt).scalar_one_or_none()

            if intelligence is None:
                intelligence = ImageIntelligence(
                    image_id=entity_id,
                    md5=md5,
                    status="queued",
                    image_path=image_path,
                    version=transaction_id,
                )
                session.add(intelligence)
            else:
                intelligence.md5 = md5
                intelligence.status = "queued"
                intelligence.image_path = image_path
                intelligence.version = transaction_id

            session.commit()

            # Trigger async jobs (face detection & CLIP embedding)
            # Create a mock StoreConfig from MInsightConfig
            from ..store.config import StoreConfig
            store_config = StoreConfig(
                cl_server_dir=self.config.cl_server_dir,
                media_storage_dir=self.config.media_storage_dir,
                public_key_path=self.config.public_key_path,
                auth_disabled=self.config.auth_disabled,
                server_port=self.config.server_port,
                mqtt_broker=self.config.mqtt_broker,
                mqtt_port=self.config.mqtt_port,
            )
            
            intelligence_service = MInsightEmbeddingService(session, store_config)
            await intelligence_service.trigger_async_jobs(entity_version)
            
            logger.info(f"Image intelligence jobs triggered for {entity_id}")

        except Exception as e:
            logger.error(f"Failed to enqueue image {entity_id} for intelligence: {e}")
            session.rollback()
        finally:
            session.close()

    def _get_last_version(self) -> int:
        """Get last processed version from sync state.

        Uses atomic database read - opens session, reads, closes.

        Returns:
            Last processed version number (0 if not found)
        """
        if not database.SessionLocal:
            raise RuntimeError("Database not initialized")

        session = database.SessionLocal()
        try:
            stmt = select(EntitySyncState).where(EntitySyncState.id == 1)
            sync_state = session.execute(stmt).scalar_one_or_none()

            if sync_state is None:
                # Create initial sync state (atomic write)
                sync_state = EntitySyncState(id=1, last_version=0)
                session.add(sync_state)
                session.commit()
                return 0

            return sync_state.last_version
        finally:
            session.close()

    def _update_last_version(self, version: int) -> None:
        """Update last processed version in sync state.

        Uses atomic database write - opens session, updates, commits, closes.

        Args:
            version: New version number
        """
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
        """Get entity changes since last version, coalesced by entity ID.

        Uses atomic database read - opens session, reads all versions, closes,
        then returns Pydantic models (no session dependency).

        Args:
            last_version: Last processed version

        Returns:
            Dict mapping entity_id to EntityVersionData (latest version per entity)
        """
        if not database.SessionLocal:
            raise RuntimeError("Database not initialized")

        session = database.SessionLocal()
        try:
            # Query all versions > last_version, ordered by transaction_id
            stmt = (
                select(self.EntityVersion)
                .where(self.EntityVersion.transaction_id > last_version)
                .order_by(self.EntityVersion.transaction_id)
            )
            versions = session.execute(stmt).scalars().all()

            # Coalesce: keep only latest version per entity
            # Convert to Pydantic models immediately (no session dependency)
            entity_map: dict[int, EntityVersionData] = {}
            for version in versions:
                entity_map[version.id] = EntityVersionData.model_validate(version)

            return entity_map
        finally:
            # Session closed - all data is in Pydantic models
            session.close()

    async def run_once(self) -> int:
        """Perform one reconciliation cycle of entity changes.

        This method uses multiple atomic database operations:
        1. Read last version (atomic)
        2. Read entity deltas (atomic)
        3. Update version marker (atomic)
        4. Process each image (each with atomic read + write)

        Returns:
            Number of images processed
        """
        # Atomic read: Get last processed version
        last_version = self._get_last_version()
        logger.info(f"Starting reconciliation from version {last_version}")

        # Atomic read: Get entity deltas (returns Pydantic models, session closed)
        entity_deltas = self._get_entity_deltas(last_version)

        if not entity_deltas:
            logger.debug("No new entity changes")
            return 0

        # Find max transaction_id for version update
        max_transaction_id = max(
            (version.transaction_id for version in entity_deltas.values()), default=last_version
        )

        if self.broadcaster:
            self.broadcaster.publish_start(
                version_start=last_version, version_end=max_transaction_id
            )

        # Process each image (each process() call has its own atomic operations)
        processed_count = 0
        for entity_version in entity_deltas.values():
            if await self.process(entity_version):
                processed_count += 1

        # Atomic write: Update last version AFTER processing (crash-safety)
        # This ensures if we crash mid-process, we'll re-process from the previous version marker
        self._update_last_version(max_transaction_id)
        logger.debug(f"Advanced version to {max_transaction_id}")

        if self.broadcaster:
            self.broadcaster.publish_end(processed_count=processed_count)

        logger.info(f"Reconciliation complete: processed {processed_count} images")
        return processed_count


__all__ = ["mInsight"]
