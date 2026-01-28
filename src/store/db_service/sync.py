from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger
from sqlalchemy.orm import Session

from .base import BaseDBService, timed
from . import database
from .database import with_retry
from .models import EntitySyncState
from .schemas import EntitySyncStateSchema

if TYPE_CHECKING:
    from ..common.config import BaseConfig


class EntitySyncStateDBService(BaseDBService[EntitySyncStateSchema]):
    model_class = EntitySyncState
    schema_class = EntitySyncStateSchema

    @timed
    @with_retry(max_retries=10)
    def get_or_create(self) -> EntitySyncStateSchema:
        """Get singleton sync state, create if doesn't exist."""
        db = self.db if self.db else database.SessionLocal()
        should_close = self.db is None
        try:
            obj = db.query(EntitySyncState).filter(EntitySyncState.id == 1).first()
            if not obj:
                obj = EntitySyncState(id=1, last_version=0)
                db.add(obj)
                db.commit()
                db.refresh(obj)
            return self._to_schema(obj)
        except Exception:
            db.rollback()
            raise
        finally:
            if should_close:
                db.close()

    @timed
    @with_retry(max_retries=10)
    def get_last_version(self) -> int:
        """Get last processed version (shorthand)."""
        state = self.get_or_create()
        return state.last_version

    @timed
    @with_retry(max_retries=10)
    def update_last_version(self, version: int) -> EntitySyncStateSchema:
        """Update last processed version."""
        db = self.db if self.db else database.SessionLocal()
        should_close = self.db is None
        try:
            obj = db.query(EntitySyncState).filter(EntitySyncState.id == 1).first()
            if not obj:
                # Create if doesn't exist
                obj = EntitySyncState(id=1, last_version=version)
                db.add(obj)
            else:
                obj.last_version = version

            db.commit()
            db.refresh(obj)
            return self._to_schema(obj)
        except Exception:
            db.rollback()
            raise
        finally:
            if should_close:
                db.close()

    # Override base methods to prevent misuse
    def create(self, data: Any, ignore_exception: bool = False) -> Any:
        raise NotImplementedError("Use get_or_create() for singleton EntitySyncState")

    def delete(self, id: int) -> bool:
        raise NotImplementedError("Cannot delete singleton EntitySyncState")
