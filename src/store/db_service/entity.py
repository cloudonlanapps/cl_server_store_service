from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, configure_mappers
from sqlalchemy_continuum import version_class  # type: ignore

from .base import BaseDBService, timed
from . import database
from .database import with_retry
from .exceptions import ResourceNotFoundError
from .models import (
    Entity,
    Face,
    KnownPerson,
)
from .schemas import EntityIntelligenceData, EntitySchema, EntityVersionSchema

if TYPE_CHECKING:
    from ..common.config import BaseConfig


def _now_timestamp() -> int:
    from datetime import UTC, datetime
    return int(datetime.now(UTC).timestamp() * 1000)


class EntityDBService(BaseDBService[EntitySchema]):
    model_class = Entity
    schema_class = EntitySchema

    def get_or_raise(self, id: int) -> EntitySchema:
        """Get entity by ID or raise ResourceNotFoundError."""
        entity = self.get(id)
        if not entity:
            raise ResourceNotFoundError(f"Entity {id} not found")
        return entity

    @timed
    @with_retry(max_retries=10)
    @timed
    @with_retry(max_retries=10)
    def update_intelligence_data(self, id: int, data: EntityIntelligenceData) -> EntitySchema | None:
        """Update intelligence_data JSON field."""
        db = self.db if self.db else database.SessionLocal()
        should_close = self.db is None
        try:
            entity = db.query(Entity).filter(Entity.id == id).first()
            if not entity:
                return None
            
            entity.intelligence_data = data.model_dump()
            db.commit()
            db.refresh(entity)
            return self._to_schema(entity)
        except Exception:
            db.rollback()
            raise
        finally:
            if should_close:
                db.close()

    def _log_cascade_deletes(self, orm_obj: Entity, db: Session) -> None:
        """Log what will be cascade deleted."""
        try:
            faces_count = len(orm_obj.faces)

            logger.info(f"Deleting Entity {orm_obj.id} will cascade delete:")
            logger.info(f"  - Faces: {faces_count}")
        except Exception as e:
            logger.warning(f"Failed to log cascade deletes for Entity {orm_obj.id}: {e}")



    @timed
    @with_retry(max_retries=10)
    def get_children(self, parent_id: int) -> list[EntitySchema]:
        """Get all child entities of a parent."""
        return self.query(parent_id=parent_id)

    @timed
    @with_retry(max_retries=10)
    @timed
    @with_retry(max_retries=10)
    def delete_all(self) -> None:
        """Bulk delete all entities and related data (for tests/admin)."""
        db = self.db if self.db else database.SessionLocal()
        should_close = self.db is None
        try:
            # Delete related data first (order matters for FKs)
            db.query(Face).delete()
            db.query(KnownPerson).delete()

            # Clear Continuum version tables
            # Note: table names might differ if configured differently, but defaults are usually pluralized + _version
            # or just _version suffix.
            # Plan lists: "entities_version", "known_persons_version", "transaction_changes", "transaction"
            for table in ["entities_version", "known_persons_version", "transaction_changes", "transaction"]:
                try:
                    db.execute(text(f"DELETE FROM {table}"))
                except Exception as e:
                    logger.warning(f"Failed to clear table {table}: {e}")

            # Delete all entities
            db.query(Entity).delete()

            # Reset sqlite sequence
            try:
                db.execute(text("DELETE FROM sqlite_sequence"))
            except Exception as e:
                logger.debug(f"sqlite_sequence clear failed: {e}")

            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            if should_close:
                db.close()


class EntityVersionDBService:
    def __init__(self, db: Session | None = None):
        # Get the EntityVersion model class
        configure_mappers()
        self.EntityVersion = version_class(Entity)
        self.db = db

    @timed
    @with_retry(max_retries=10)
    def get_all_for_entity(self, entity_id: int) -> list[EntityVersionSchema]:
        """Get all versions of a specific entity.

        Works even if entity is deleted from main table.
        """
        db = self.db if self.db else database.SessionLocal()
        should_close = self.db is None
        try:
            logger.debug(f"Getting all versions for entity_id={entity_id}")
            stmt = select(self.EntityVersion).where(self.EntityVersion.id == entity_id).order_by(self.EntityVersion.transaction_id)
            versions = db.execute(stmt).scalars().all()
            logger.debug(f"Found {len(versions)} versions for entity_id={entity_id}")
            return [EntityVersionSchema.model_validate(v) for v in versions]
        finally:
            if should_close:
                db.close()

    @timed
    @with_retry(max_retries=10)
    @timed
    @with_retry(max_retries=10)
    def get_by_transaction_id(self, entity_id: int, transaction_id: int) -> EntityVersionSchema | None:
        """Get specific version by entity_id and transaction_id.

        Works even if entity is deleted from main table.
        """
        db = self.db if self.db else database.SessionLocal()
        should_close = self.db is None
        try:
            logger.debug(f"Getting version entity_id={entity_id}, transaction_id={transaction_id}")
            stmt = select(self.EntityVersion).where(
                (self.EntityVersion.id == entity_id) & (self.EntityVersion.transaction_id == transaction_id)
            )
            version = db.execute(stmt).scalar_one_or_none()
            result = EntityVersionSchema.model_validate(version) if version else None
            logger.debug(f"Version {'found' if result else 'not found'}")
            return result
        finally:
            if should_close:
                db.close()

    @timed
    @with_retry(max_retries=10)
    def get_versions_in_range(
        self,
        start_transaction_id: int,
        end_transaction_id: int | None = None
    ) -> dict[int, EntityVersionSchema]:
        """Get entity changes in transaction ID range, coalesced by entity ID."""
    @timed
    @with_retry(max_retries=10)
    def get_versions_in_range(
        self,
        start_transaction_id: int,
        end_transaction_id: int | None = None
    ) -> dict[int, EntityVersionSchema]:
        """Get entity changes in transaction ID range, coalesced by entity ID."""
        db = self.db if self.db else database.SessionLocal()
        should_close = self.db is None
        try:
            if end_transaction_id is None:
                logger.debug(f"Getting entity deltas from transaction_id > {start_transaction_id} to latest")
                stmt = (
                    select(self.EntityVersion)
                    .where(self.EntityVersion.transaction_id > start_transaction_id)
                    .order_by(self.EntityVersion.transaction_id)
                )
            else:
                logger.debug(f"Getting entity deltas from transaction_id > {start_transaction_id} to <= {end_transaction_id}")
                stmt = (
                    select(self.EntityVersion)
                    .where(
                        (self.EntityVersion.transaction_id > start_transaction_id) &
                        (self.EntityVersion.transaction_id <= end_transaction_id)
                    )
                    .order_by(self.EntityVersion.transaction_id)
                )

            versions = db.execute(stmt).scalars().all()

            # Coalesce by entity_id (keep latest version per entity in range)
            entity_map: dict[int, EntityVersionSchema] = {}
            for version in versions:
                entity_map[version.id] = EntityVersionSchema.model_validate(version)

            logger.debug(f"Found {len(entity_map)} entities with changes in range")
            return entity_map
        finally:
            if should_close:
                db.close()

    @timed
    @with_retry(max_retries=10)
    def query(self, **kwargs: Any) -> list[EntityVersionSchema]:
        """Query version table with filters."""
    @timed
    @with_retry(max_retries=10)
    def query(self, **kwargs: Any) -> list[EntityVersionSchema]:
        """Query version table with filters."""
        db = self.db if self.db else database.SessionLocal()
        should_close = self.db is None
        try:
            logger.debug(f"Querying EntityVersion with filters: {kwargs}")
            filters = []
            for key, value in kwargs.items():
                if '__' in key:
                    field_name, operator = key.rsplit('__', 1)
                    if hasattr(self.EntityVersion, field_name):
                         column = getattr(self.EntityVersion, field_name)
                         if operator == 'gt':
                             filters.append(column > value)
                         elif operator == 'gte':
                             filters.append(column >= value)
                         elif operator == 'lt':
                             filters.append(column < value)
                         elif operator == 'lte':
                             filters.append(column <= value)
                         elif operator == 'ne':
                             filters.append(column != value)
                else:
                    if hasattr(self.EntityVersion, key):
                        filters.append(getattr(self.EntityVersion, key) == value)

            stmt = select(self.EntityVersion).where(*filters)
            results = db.execute(stmt).scalars().all()
            logger.debug(f"Found {len(results)} EntityVersion records")
            return [EntityVersionSchema.model_validate(r) for r in results]
        finally:
            if should_close:
                db.close()
