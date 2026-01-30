from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from loguru import logger
from store.db_service import database
from store.db_service.base import BaseDBService, timed
from store.db_service.database import with_retry
from store.db_service.models import Entity, EntityIntelligence
from store.db_service.schemas import EntityIntelligenceData

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class EntityIntelligenceDBService:
    """Service for handling Entity Intelligence data (sidecar table)."""

    def __init__(self, db: Session | None = None):
        self.db = db

    @timed
    @with_retry(max_retries=10)
    def get_intelligence_data(self, entity_id: int) -> EntityIntelligenceData | None:
        """Get intelligence data for an entity."""
        db = self.db if self.db else database.SessionLocal()
        should_close = self.db is None
        try:
            intelligence = (
                db.query(EntityIntelligence)
                .filter(EntityIntelligence.entity_id == entity_id)
                .first()
            )
            
            if not intelligence or not intelligence.intelligence_data:
                return None
                
            return EntityIntelligenceData.model_validate(intelligence.intelligence_data)
        finally:
            if should_close:
                db.close()

    @timed
    @with_retry(max_retries=10)
    def update_intelligence_data(
        self, id: int, data: EntityIntelligenceData
    ) -> EntityIntelligenceData | None:
        """Update intelligence_data in sidecar table."""
        db = self.db if self.db else database.SessionLocal()
        should_close = self.db is None
        try:
            intel = db.query(EntityIntelligence).filter(EntityIntelligence.entity_id == id).first()
            
            if not intel:
                # Ensure entity exists before creating intelligence record
                if not db.query(Entity.id).filter(Entity.id == id).scalar():
                    return None
                    
                intel = EntityIntelligence(
                    entity_id=id, intelligence_data=data.model_dump()
                )
                db.add(intel)
            else:
                intel.intelligence_data = data.model_dump()

            db.commit()
            db.refresh(intel)
            
            if intel.intelligence_data:
                return EntityIntelligenceData.model_validate(intel.intelligence_data)
            return None
        except Exception:
            db.rollback()
            raise
        finally:
            if should_close:
                db.close()

    @timed
    @with_retry(max_retries=10)
    def atomic_update_intelligence_data(
        self, id: int, update_fn: Callable[[EntityIntelligenceData], None]
    ) -> EntityIntelligenceData | None:
        """Atomically read-modify-write intelligence_data with row-level locking."""
        db = self.db if self.db else database.SessionLocal()
        should_close = self.db is None
        try:
            # Lock the intelligence record directly
            intel = (
                db.query(EntityIntelligence)
                .filter(EntityIntelligence.entity_id == id)
                .with_for_update()
                .first()
            )

            # Lazy initialization if missing
            if not intel:
                # Check entity existence (no lock on Entity needed, just existence)
                if not db.query(Entity.id).filter(Entity.id == id).scalar():
                    return None
                
                logger.info(f"Initializing missing EntityIntelligence for entity {id}")
                from datetime import datetime, UTC
                now = int(datetime.now(UTC).timestamp() * 1000)
                
                intel = EntityIntelligence(
                    entity_id=id, 
                    intelligence_data=EntityIntelligenceData(last_updated=now).model_dump()
                )
                db.add(intel)
                # Flush to ensure it exists for subsequent operations if needed
                db.flush() 
            
            if not intel.intelligence_data:
                 from datetime import datetime, UTC
                 now = int(datetime.now(UTC).timestamp() * 1000)
                 intel.intelligence_data = EntityIntelligenceData(last_updated=now).model_dump()

            # Parse current data
            data = EntityIntelligenceData.model_validate(intel.intelligence_data)

            # Apply the update function
            update_fn(data)

            # Update timestamp
            from datetime import datetime, UTC
            data.last_updated = int(datetime.now(UTC).timestamp() * 1000)

            # Write back
            intel.intelligence_data = data.model_dump()
            db.commit()
            
            return data
        except Exception:
            db.rollback()
            raise
        finally:
            if should_close:
                db.close()
