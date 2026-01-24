from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger
from sqlalchemy.orm import Session

from .base import BaseDBService, timed
from . import database
from .database import with_retry
from .models import Entity, Face, FaceMatch, KnownPerson
from .schemas import FaceMatchSchema, FaceSchema, KnownPersonSchema

if TYPE_CHECKING:
    from ..common.config import BaseConfig


def _now_timestamp() -> int:
    from datetime import UTC, datetime
    return int(datetime.now(UTC).timestamp() * 1000)


class FaceDBService(BaseDBService[FaceSchema]):
    model_class = Face
    schema_class = FaceSchema

    def _log_cascade_deletes(self, orm_obj: Face, db: Session) -> None:
        """Log what will be cascade deleted."""
        try:
            # Count FaceMatch records that will be deleted
            match_count = db.query(FaceMatch).filter(
                (FaceMatch.face_id == orm_obj.id) | (FaceMatch.matched_face_id == orm_obj.id)
            ).count()

            logger.info(f"Deleting Face {orm_obj.id} (entity_id={orm_obj.entity_id}) will cascade delete:")
            logger.info(f"  - FaceMatch records: {match_count}")
        except Exception as e:
            logger.warning(f"Failed to log cascade deletes for Face {orm_obj.id}: {e}")

    @timed
    @with_retry(max_retries=10)
    def get_by_entity_id(self, entity_id: int) -> list[FaceSchema]:
        """Get all faces for an entity."""
        db = database.SessionLocal()
        try:
            objs = db.query(Face).filter(Face.entity_id == entity_id).all()
            return [self._to_schema(obj) for obj in objs]
        finally:
            db.close()

    @timed
    @with_retry(max_retries=10)
    def get_by_known_person_id(self, known_person_id: int) -> list[FaceSchema]:
        """Get all faces for a known person."""
        db = database.SessionLocal()
        try:
            objs = db.query(Face).filter(Face.known_person_id == known_person_id).all()
            return [self._to_schema(obj) for obj in objs]
        finally:
            db.close()

    @timed
    @with_retry(max_retries=10)
    def count_by_entity_id(self, entity_id: int) -> int:
        """Count faces for an entity."""
        db = database.SessionLocal()
        try:
            return db.query(Face).filter(Face.entity_id == entity_id).count()
        finally:
            db.close()

    @timed
    @with_retry(max_retries=10)
    def count_by_known_person_id(self, known_person_id: int) -> int:
        """Count faces for a known person."""
        db = database.SessionLocal()
        try:
            return db.query(Face).filter(Face.known_person_id == known_person_id).count()
        finally:
            db.close()

    @timed
    @with_retry(max_retries=10)
    def create_or_update(self, data: FaceSchema, ignore_exception: bool = False) -> FaceSchema | None:
        """Upsert face (deterministic ID: entity_id * 10000 + index).

        Args:
            data: Face data
            ignore_exception: If True, return None on errors (e.g., entity deleted during callback)
        """
        db = database.SessionLocal()
        try:
            # Check if entity exists before writing face
            entity_exists = db.query(Entity.id).filter(Entity.id == data.entity_id).scalar() is not None
            if not entity_exists:
                logger.debug(f"Entity {data.entity_id} not found, skipping Face create/update")
                if ignore_exception:
                    return None
                raise ValueError(f"Entity {data.entity_id} does not exist")

            logger.debug(f"Creating/updating Face id={data.id} for entity_id={data.entity_id}")
            obj = db.query(Face).filter(Face.id == data.id).first()
            if obj:
                # Update existing
                logger.debug(f"Updating existing Face id={data.id}")
                for key, value in data.model_dump(exclude_unset=True).items():
                    setattr(obj, key, value)
            else:
                # Create new
                logger.debug(f"Creating new Face id={data.id}")
                obj = Face(**data.model_dump(exclude_unset=True))
                db.add(obj)

            db.commit()
            db.refresh(obj)
            logger.debug(f"Face id={data.id} saved")
            return self._to_schema(obj)
        except Exception as e:
            db.rollback()
            if ignore_exception:
                logger.debug(f"Ignoring exception for Face id={data.id}: {e}")
                return None
            logger.error(f"Failed to create/update Face id={data.id}: {e}")
            raise
        finally:
            db.close()

    @timed
    @with_retry(max_retries=10)
    def update_known_person_id(self, face_id: int, known_person_id: int | None) -> FaceSchema | None:
        """Link/unlink face to known person."""
        db = database.SessionLocal()
        try:
            obj = db.query(Face).filter(Face.id == face_id).first()
            if not obj:
                return None

            obj.known_person_id = known_person_id
            db.commit()
            db.refresh(obj)
            return self._to_schema(obj)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


class KnownPersonDBService(BaseDBService[KnownPersonSchema]):
    model_class = KnownPerson
    schema_class = KnownPersonSchema

    @timed
    @with_retry(max_retries=10)
    def delete(self, id: int) -> bool:
        """Delete person only if no faces linked."""
        db = database.SessionLocal()
        try:
            person = db.query(KnownPerson).filter_by(id=id).first()
            if not person:
                return False

            # Check for linked faces
            face_count = db.query(Face).filter_by(known_person_id=id).count()
            if face_count > 0:
                raise ValueError(
                    f"Cannot delete KnownPerson {id}: {face_count} Face(s) are linked. "
                    f"Unlink faces first by setting their known_person_id to NULL."
                )

            db.delete(person)
            db.commit()
            return True
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @timed
    @with_retry(max_retries=10)
    def create_with_flush(self) -> KnownPersonSchema:
        """Create new person and flush to get ID (for immediate linking)."""
        db = database.SessionLocal()
        try:
            now = _now_timestamp()
            obj = KnownPerson(created_at=now, updated_at=now)
            db.add(obj)
            db.flush()  # Get ID without committing
            db.commit()
            db.refresh(obj)
            return self._to_schema(obj)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @timed
    @with_retry(max_retries=10)
    def update_name(self, person_id: int, name: str) -> KnownPersonSchema | None:
        """Update person name."""
        db = database.SessionLocal()
        try:
            obj = db.query(KnownPerson).filter(KnownPerson.id == person_id).first()
            if not obj:
                return None

            obj.name = name
            obj.updated_at = _now_timestamp()
            db.commit()
            db.refresh(obj)
            return self._to_schema(obj)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @timed
    @with_retry(max_retries=10)
    def exists(self, person_id: int) -> bool:
        """Check if person exists."""
        db = database.SessionLocal()
        try:
            return db.query(KnownPerson.id).filter(KnownPerson.id == person_id).scalar() is not None
        finally:
            db.close()


class FaceMatchDBService(BaseDBService[FaceMatchSchema]):
    model_class = FaceMatch
    schema_class = FaceMatchSchema

    @timed
    @with_retry(max_retries=10)
    def get_by_face_id(self, face_id: int) -> list[FaceMatchSchema]:
        """Get all matches for a face."""
        db = database.SessionLocal()
        try:
            objs = db.query(FaceMatch).filter(FaceMatch.face_id == face_id).all()
            return [self._to_schema(obj) for obj in objs]
        finally:
            db.close()

    @timed
    @with_retry(max_retries=10)
    def count_by_face_id(self, face_id: int) -> int:
        """Count matches for a face (for delete logging)."""
        db = database.SessionLocal()
        try:
            return db.query(FaceMatch).filter(
                (FaceMatch.face_id == face_id) | (FaceMatch.matched_face_id == face_id)
            ).count()
        finally:
            db.close()

    @timed
    @with_retry(max_retries=10)
    def create_batch(self, matches: list[FaceMatchSchema], ignore_exception: bool = False) -> list[FaceMatchSchema]:
        """Create multiple match records in single transaction."""
        db = database.SessionLocal()
        try:
            logger.debug(f"Creating batch of {len(matches)} FaceMatch records")
            objs = [FaceMatch(**m.model_dump(exclude_unset=True)) for m in matches]
            db.add_all(objs)
            db.commit()
            for obj in objs:
                db.refresh(obj)
            logger.debug(f"Created {len(objs)} FaceMatch records")
            return [self._to_schema(obj) for obj in objs]
        except Exception as e:
            db.rollback()
            if ignore_exception:
                logger.debug(f"Ignoring exception for FaceMatch batch create: {e}")
                return []
            logger.error(f"Failed to create FaceMatch batch: {e}")
            raise
        finally:
            db.close()
