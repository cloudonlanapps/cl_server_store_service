from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, configure_mappers
from sqlalchemy_continuum import version_class  # type: ignore

from .base import BaseDBService, timed
from . import database
from .database import with_retry
from .models import (
    Entity,
    EntityJob,
    Face,
    FaceMatch,
    ImageIntelligence,
    KnownPerson,
)
from .schemas import EntitySchema, EntityVersionSchema

if TYPE_CHECKING:
    from ..common.config import BaseConfig


def _now_timestamp() -> int:
    from datetime import UTC, datetime
    return int(datetime.now(UTC).timestamp() * 1000)


class EntityDBService(BaseDBService[EntitySchema]):
    model_class = Entity
    schema_class = EntitySchema

    def _log_cascade_deletes(self, orm_obj: Entity, db: Session) -> None:
        """Log what will be cascade deleted."""
        # Note: orm_obj might not have relationships loaded if session closed?
        # But BaseDBService.delete keeps session open while calling this.
        # However, we need to be careful about lazy loading. 
        # But usually accessing attributes triggers load if session is active.
        
        # Actually, counting is better to avoid loading everything.
        try:
            intelligence_count = 1 if orm_obj.intelligence else 0
            faces_count = len(orm_obj.faces)
            jobs_count = len(orm_obj.jobs)

            logger.info(f"Deleting Entity {orm_obj.id} will cascade delete:")
            logger.info(f"  - ImageIntelligence: {intelligence_count}")
            logger.info(f"  - Faces: {faces_count}")
            logger.info(f"  - EntityJobs: {jobs_count}")
        except Exception as e:
            logger.warning(f"Failed to log cascade deletes for Entity {orm_obj.id}: {e}")

    @timed
    @with_retry(max_retries=10)
    def get_with_intelligence_status(self, id: int) -> tuple[EntitySchema | None, str | None]:
        """Get entity with intelligence status via outer join."""
        db = database.SessionLocal()
        try:
            result = db.query(Entity, ImageIntelligence.status)\
                .outerjoin(ImageIntelligence, Entity.id == ImageIntelligence.entity_id)\
                .filter(Entity.id == id)\
                .first()
            if result:
                # result is tuple (Entity, status_str)
                entity, status = result
                return (self._to_schema(entity), status)
            return (None, None)
        finally:
            db.close()

    @timed
    @with_retry(max_retries=10)
    def get_all_with_intelligence_status(
        self,
        page: int | None = 1,
        page_size: int = 20,
        exclude_deleted: bool = False
    ) -> list[tuple[EntitySchema, str | None]] | tuple[list[tuple[EntitySchema, str | None]], int]:
        """Get all entities with intelligence status via outer join."""
        db = database.SessionLocal()
        try:
            query = db.query(Entity, ImageIntelligence.status)\
                .outerjoin(ImageIntelligence, Entity.id == ImageIntelligence.entity_id)

            if exclude_deleted:
                query = query.filter(Entity.is_deleted == False)

            if page is None:
                results = query.all()
                return [(self._to_schema(e), s) for e, s in results]
            else:
                total = query.count()
                offset = (page - 1) * page_size
                results = query.order_by(Entity.id.asc()).offset(offset).limit(page_size).all()
                items = [(self._to_schema(e), s) for e, s in results]
                return (items, total)
        finally:
            db.close()

    @timed
    @with_retry(max_retries=10)
    def get_children(self, parent_id: int) -> list[EntitySchema]:
        """Get all child entities of a parent."""
        return self.query(parent_id=parent_id)

    @timed
    @with_retry(max_retries=10)
    def delete_all(self) -> None:
        """Bulk delete all entities and related data (for tests/admin)."""
        db = database.SessionLocal()
        try:
            # Delete related data first (order matters for FKs)
            db.query(EntityJob).delete()
            db.query(FaceMatch).delete()
            db.query(Face).delete()
            db.query(ImageIntelligence).delete()
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
            db.close()


class EntityVersionDBService:
    def __init__(self):
        # Get the EntityVersion model class
        configure_mappers()
        self.EntityVersion = version_class(Entity)

    @timed
    @with_retry(max_retries=10)
    def get_all_for_entity(self, entity_id: int) -> list[EntityVersionSchema]:
        """Get all versions of a specific entity.

        Works even if entity is deleted from main table.
        """
        db = database.SessionLocal()
        try:
            logger.debug(f"Getting all versions for entity_id={entity_id}")
            stmt = select(self.EntityVersion).where(self.EntityVersion.id == entity_id).order_by(self.EntityVersion.transaction_id)
            versions = db.execute(stmt).scalars().all()
            logger.debug(f"Found {len(versions)} versions for entity_id={entity_id}")
            return [EntityVersionSchema.model_validate(v) for v in versions]
        finally:
            db.close()

    @timed
    @with_retry(max_retries=10)
    def get_by_transaction_id(self, entity_id: int, transaction_id: int) -> EntityVersionSchema | None:
        """Get specific version by entity_id and transaction_id.

        Works even if entity is deleted from main table.
        """
        db = database.SessionLocal()
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
            db.close()

    @timed
    @with_retry(max_retries=10)
    def get_versions_in_range(
        self,
        start_transaction_id: int,
        end_transaction_id: int | None = None
    ) -> dict[int, EntityVersionSchema]:
        """Get entity changes in transaction ID range, coalesced by entity ID."""
        db = database.SessionLocal()
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
            db.close()

    @timed
    @with_retry(max_retries=10)
    def query(self, **kwargs: Any) -> list[EntityVersionSchema]:
        """Query version table with filters."""
        db = database.SessionLocal()
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
            db.close()
