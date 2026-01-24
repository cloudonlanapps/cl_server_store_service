from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger
from sqlalchemy.orm import Session

from .base import BaseDBService, timed
from . import database
from .database import with_retry
from .models import Entity, EntityJob, ImageIntelligence
from .schemas import EntityJobSchema, ImageIntelligenceSchema

if TYPE_CHECKING:
    from ..common.config import BaseConfig


def _now_timestamp() -> int:
    from datetime import UTC, datetime
    return int(datetime.now(UTC).timestamp() * 1000)


class ImageIntelligenceDBService(BaseDBService[ImageIntelligenceSchema]):
    model_class = ImageIntelligence
    schema_class = ImageIntelligenceSchema

    @timed
    @with_retry(max_retries=10)
    def get_by_entity_id(self, entity_id: int) -> ImageIntelligenceSchema | None:
        """Get by entity_id (primary key)."""
        db = database.SessionLocal()
        try:
            logger.debug(f"Getting ImageIntelligence for entity_id={entity_id}")
            obj = db.query(ImageIntelligence).filter(ImageIntelligence.entity_id == entity_id).first()
            result = self._to_schema(obj) if obj else None
            logger.debug(f"ImageIntelligence entity_id={entity_id}: {'found' if result else 'not found'}")
            return result
        finally:
            db.close()

    @timed
    @with_retry(max_retries=10)
    def create_or_update(self, data: ImageIntelligenceSchema, ignore_exception: bool = False) -> ImageIntelligenceSchema | None:
        """Upsert intelligence record.

        Args:
            data: Intelligence data
            ignore_exception: If True, return None on errors (e.g., entity deleted during callback)
        """
        db = database.SessionLocal()
        try:
            # Check if entity exists before writing
            entity_exists = db.query(Entity.id).filter(Entity.id == data.entity_id).scalar() is not None
            if not entity_exists:
                logger.debug(f"Entity {data.entity_id} not found, skipping ImageIntelligence create/update")
                if ignore_exception:
                    return None
                raise ValueError(f"Entity {data.entity_id} does not exist")

            logger.debug(f"Creating/updating ImageIntelligence for entity_id={data.entity_id}")
            # Use query to get object
            obj = db.query(ImageIntelligence).filter(ImageIntelligence.entity_id == data.entity_id).first()
            if obj:
                # Update existing
                logger.debug(f"Updating existing ImageIntelligence for entity_id={data.entity_id}")
                for key, value in data.model_dump(exclude_unset=True).items():
                    setattr(obj, key, value)
            else:
                # Create new
                logger.debug(f"Creating new ImageIntelligence for entity_id={data.entity_id}")
                obj = ImageIntelligence(**data.model_dump(exclude_unset=True))
                db.add(obj)

            db.commit()
            db.refresh(obj)
            logger.debug(f"ImageIntelligence for entity_id={data.entity_id} saved")
            return self._to_schema(obj)
        except Exception as e:
            db.rollback()
            if ignore_exception:
                logger.debug(f"Ignoring exception for ImageIntelligence entity_id={data.entity_id}: {e}")
                return None
            logger.error(f"Failed to create/update ImageIntelligence entity_id={data.entity_id}: {e}")
            raise
        finally:
            db.close()

    @timed
    @with_retry(max_retries=10)
    def update_job_ids(self, entity_id: int, ignore_exception: bool = False, **job_ids: Any) -> ImageIntelligenceSchema | None:
        """Update specific job ID fields."""
        db = database.SessionLocal()
        try:
            # Check if entity exists
            entity_exists = db.query(Entity.id).filter(Entity.id == entity_id).scalar() is not None
            if not entity_exists:
                logger.debug(f"Entity {entity_id} not found, skipping job ID update")
                if ignore_exception:
                    return None
                raise ValueError(f"Entity {entity_id} does not exist")

            logger.debug(f"Updating ImageIntelligence job IDs for entity_id={entity_id}: {job_ids}")
            obj = db.query(ImageIntelligence).filter(ImageIntelligence.entity_id == entity_id).first()
            if not obj:
                logger.debug(f"ImageIntelligence not found for entity_id={entity_id}")
                return None

            for key, value in job_ids.items():
                if hasattr(obj, key):
                     setattr(obj, key, value)

            db.commit()
            db.refresh(obj)
            logger.debug(f"Updated ImageIntelligence job IDs for entity_id={entity_id}")
            return self._to_schema(obj)
        except Exception as e:
            db.rollback()
            if ignore_exception:
                logger.debug(f"Ignoring exception for ImageIntelligence update entity_id={entity_id}: {e}")
                return None
            logger.error(f"Failed to update ImageIntelligence job IDs entity_id={entity_id}: {e}")
            raise
        finally:
            db.close()


class EntityJobDBService(BaseDBService[EntityJobSchema]):
    model_class = EntityJob
    schema_class = EntityJobSchema

    @timed
    @with_retry(max_retries=10)
    def get_by_job_id(self, job_id: str) -> EntityJobSchema | None:
        """Get job by job_id (unique field)."""
        db = database.SessionLocal()
        try:
            logger.debug(f"Getting EntityJob by job_id={job_id}")
            obj = db.query(EntityJob).filter(EntityJob.job_id == job_id).first()
            result = self._to_schema(obj) if obj else None
            logger.debug(f"EntityJob job_id={job_id}: {'found' if result else 'not found'}")
            return result
        finally:
            db.close()

    @timed
    @with_retry(max_retries=10)
    def get_by_entity_id(self, entity_id: int) -> list[EntityJobSchema]:
        """Get all jobs for an entity."""
        db = database.SessionLocal()
        try:
            logger.debug(f"Getting EntityJobs for entity_id={entity_id}")
            objs = db.query(EntityJob).filter(EntityJob.entity_id == entity_id).all()
            logger.debug(f"Found {len(objs)} EntityJobs for entity_id={entity_id}")
            return [self._to_schema(obj) for obj in objs]
        finally:
            db.close()

    @timed
    @with_retry(max_retries=10)
    def create(self, data: EntityJobSchema, ignore_exception: bool = False) -> EntityJobSchema | None:
        """Create job record."""
        db = database.SessionLocal()
        try:
            # Check if entity exists before creating job
            entity_exists = db.query(Entity.id).filter(Entity.id == data.entity_id).scalar() is not None
            if not entity_exists:
                logger.debug(f"Entity {data.entity_id} not found, skipping EntityJob create")
                if ignore_exception:
                    return None
                raise ValueError(f"Entity {data.entity_id} does not exist")

            logger.debug(f"Creating EntityJob for entity_id={data.entity_id}, job_id={data.job_id}")
            obj = EntityJob(**data.model_dump(exclude_unset=True))
            db.add(obj)
            db.commit()
            db.refresh(obj)
            logger.debug(f"Created EntityJob id={obj.id}")
            return self._to_schema(obj)
        except Exception as e:
            db.rollback()
            if ignore_exception:
                logger.debug(f"Ignoring exception for EntityJob create: {e}")
                return None
            logger.error(f"Failed to create EntityJob: {e}")
            raise
        finally:
            db.close()

    @timed
    @with_retry(max_retries=10)
    def update_status(
        self,
        job_id: str,
        status: str,
        error_message: str | None = None,
        completed_at: int | None = None,
        ignore_exception: bool = False
    ) -> tuple[EntityJobSchema | None, int | None]:
        """Update job status, returns (job, entity_id) for broadcasting."""
        db = database.SessionLocal()
        try:
            logger.debug(f"Updating EntityJob status job_id={job_id} to {status}")
            obj = db.query(EntityJob).filter(EntityJob.job_id == job_id).first()
            if not obj:
                logger.debug(f"EntityJob job_id={job_id} not found")
                return (None, None)

            obj.status = status
            obj.updated_at = _now_timestamp()
            if error_message:
                obj.error_message = error_message
            if completed_at:
                obj.completed_at = completed_at

            db.commit()
            db.refresh(obj)
            logger.debug(f"Updated EntityJob job_id={job_id} status to {status}")
            return (self._to_schema(obj), obj.entity_id)
        except Exception as e:
            db.rollback()
            if ignore_exception:
                logger.debug(f"Ignoring exception for EntityJob status update job_id={job_id}: {e}")
                return (None, None)
            logger.error(f"Failed to update EntityJob status job_id={job_id}: {e}")
            raise
        finally:
            db.close()

    @timed
    @with_retry(max_retries=10)
    def delete_by_job_id(self, job_id: str, ignore_exception: bool = False) -> bool:
        """Delete job by job_id."""
        db = database.SessionLocal()
        try:
            logger.debug(f"Deleting EntityJob job_id={job_id}")
            obj = db.query(EntityJob).filter(EntityJob.job_id == job_id).first()
            if not obj:
                logger.debug(f"EntityJob job_id={job_id} not found for deletion")
                return False

            db.delete(obj)
            db.commit()
            logger.debug(f"Deleted EntityJob job_id={job_id}")
            return True
        except Exception as e:
            db.rollback()
            if ignore_exception:
                logger.debug(f"Ignoring exception for EntityJob delete job_id={job_id}: {e}")
                return False
            logger.error(f"Failed to delete EntityJob job_id={job_id}: {e}")
            raise
        finally:
            db.close()
