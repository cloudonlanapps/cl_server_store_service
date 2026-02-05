from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, TypeVar

from loguru import logger
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

# Try to import timed, fallback to local definition if missing (to avoid breaking if dependency missing)
try:
    from cl_ml_tools.utils.profiling import timed
except ImportError:
    import time
    from functools import wraps

    def timed(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                pass

        return wrapper


from . import database
from .database import with_retry

# Use TypeVar for Schema
SchemaT = TypeVar("SchemaT", bound=BaseModel)

if TYPE_CHECKING:
    from ..common.config import BaseConfig


class BaseDBService(Generic[SchemaT]):
    """Base class with common CRUD operations.

    CRITICAL: Each method manages its own session for multi-process safety.
    Pattern: SessionLocal() -> try/commit -> finally/close

    All methods decorated with:
    - @timed: Measure execution time (including all retries)
    - @with_retry(max_retries=10): Retry on database locks
    """

    model_class: type
    schema_class: type[SchemaT]

    def __init__(self, db: Session | None = None):
        """Initialize service."""
        self.db = db

    @timed
    @with_retry(max_retries=10)
    def get(self, id: int) -> SchemaT | None:
        """Get single record by ID.

        Session: Creates and closes own session.
        """
        db = database.SessionLocal()
        try:
            # Using filter_by matches the plan, but model_class.id == id is safer if id is not a declared attr
            # filter_by(id=id) assumes the PK is named 'id' (which it is for our models)
            obj = db.query(self.model_class).filter_by(id=id).first()
            return self._to_schema(obj) if obj else None
        finally:
            db.close()

    @timed
    @with_retry(max_retries=10)
    def get_all(
        self, page: int | None = 1, page_size: int = 20
    ) -> list[SchemaT] | tuple[list[SchemaT], int]:
        """Get all records with optional pagination.

        Session: Creates and closes own session.
        """
        db = database.SessionLocal()
        try:
            stmt = select(self.model_class)

            if page is None:
                results = db.execute(stmt).scalars().all()
                return [self._to_schema(r) for r in results]
            else:
                total = db.execute(select(func.count()).select_from(self.model_class)).scalar() or 0
                offset = (page - 1) * page_size
                results = db.execute(stmt.offset(offset).limit(page_size)).scalars().all()
                items = [self._to_schema(r) for r in results]
                return (items, total)
        finally:
            db.close()

    @timed
    @with_retry(max_retries=10)
    def create(self, data: SchemaT, ignore_exception: bool = False) -> SchemaT | None:
        """Create new record.

        Args:
            data: Schema with data to create
            ignore_exception: If True, return None on errors instead of raising (for callbacks)

        Session: Creates and closes own session.
        """
        db = database.SessionLocal()
        try:
            logger.debug(
                f"Creating {self.model_class.__name__}: {data.model_dump(exclude_unset=True)}"
            )
            # We exclude unset to allow defaults in DB or Model to take over if not provided
            # But normally creating a record should have all required fields.
            # Using exclude_unset=True matches plan.
            obj = self.model_class(**data.model_dump(exclude_unset=True))
            db.add(obj)
            db.commit()
            db.refresh(obj)
            # Safe access to id (some models might have different PK, but all ours have id)
            pk = getattr(obj, "id", "N/A")
            logger.debug(f"Created {self.model_class.__name__} with id={pk}")
            return self._to_schema(obj)
        except Exception as e:
            db.rollback()
            if ignore_exception:
                logger.debug(f"Ignoring exception during create {self.model_class.__name__}: {e}")
                return None
            logger.error(f"Failed to create {self.model_class.__name__}: {e}")
            raise
        finally:
            db.close()

    @timed
    @with_retry(max_retries=10)
    def update(self, id: int, data: SchemaT, ignore_exception: bool = False) -> SchemaT | None:
        """Update existing record.

        Args:
            id: Record ID
            data: Schema with updated data
            ignore_exception: If True, return None on errors instead of raising (for callbacks)

        Session: Creates and closes own session.
        """
        db = database.SessionLocal()
        try:
            logger.debug(
                f"Updating {self.model_class.__name__} id={id}: {data.model_dump(exclude_unset=True)}"
            )
            obj = db.query(self.model_class).filter_by(id=id).first()
            if not obj:
                logger.debug(f"{self.model_class.__name__} id={id} not found for update")
                return None

            for key, value in data.model_dump(exclude_unset=True).items():
                setattr(obj, key, value)

            db.commit()
            db.refresh(obj)
            logger.debug(f"Updated {self.model_class.__name__} id={id}")
            return self._to_schema(obj)
        except Exception as e:
            db.rollback()
            if ignore_exception:
                logger.debug(
                    f"Ignoring exception during update {self.model_class.__name__} id={id}: {e}"
                )
                return None
            logger.error(f"Failed to update {self.model_class.__name__} id={id}: {e}")
            raise
        finally:
            db.close()

    @timed
    @with_retry(max_retries=10)
    def query(
        self,
        order_by: str | None = None,
        ascending: bool = True,
        limit: int | None = None,
        offset: int | None = None,
        **kwargs: Any,
    ) -> list[SchemaT]:
        """Flexible query with operators.

        Session: Creates and closes own session.
        """
        db = database.SessionLocal()
        try:
            filters = []
            for key, value in kwargs.items():
                if "__" in key:
                    field_name, operator = key.rsplit("__", 1)
                    if not hasattr(self.model_class, field_name):
                        # Could raise error or ignore.
                        # Plan code assumes attributes exist.
                        pass
                    column = getattr(self.model_class, field_name)
                    if operator == "gt":
                        filters.append(column > value)
                    elif operator == "gte":
                        filters.append(column >= value)
                    elif operator == "lt":
                        filters.append(column < value)
                    elif operator == "lte":
                        filters.append(column <= value)
                    elif operator == "ne":
                        filters.append(column != value)
                else:
                    if hasattr(self.model_class, key):
                        filters.append(getattr(self.model_class, key) == value)

            stmt = select(self.model_class).where(*filters)

            # Apply ordering
            if order_by and hasattr(self.model_class, order_by):
                order_column = getattr(self.model_class, order_by)
                stmt = stmt.order_by(order_column.asc() if ascending else order_column.desc())

            # Apply limit/offset
            if offset:
                stmt = stmt.offset(offset)
            if limit:
                stmt = stmt.limit(limit)

            results = db.execute(stmt).scalars().all()
            return [self._to_schema(r) for r in results]
        finally:
            db.close()

    @timed
    @with_retry(max_retries=10)
    def count(self, **kwargs: Any) -> int:
        """Count records matching filters.

        Session: Creates and closes own session.
        """
        db = database.SessionLocal()
        try:
            filters = []
            for key, value in kwargs.items():
                if "__" in key:
                    field_name, operator = key.rsplit("__", 1)
                    column = getattr(self.model_class, field_name)
                    if operator == "gt":
                        filters.append(column > value)
                    elif operator == "gte":
                        filters.append(column >= value)
                    elif operator == "lt":
                        filters.append(column < value)
                    elif operator == "lte":
                        filters.append(column <= value)
                    elif operator == "ne":
                        filters.append(column != value)
                else:
                    filters.append(getattr(self.model_class, key) == value)

            stmt = select(func.count()).select_from(self.model_class).where(*filters)
            return db.execute(stmt).scalar() or 0
        finally:
            db.close()

    def _to_schema(self, orm_obj: Any) -> SchemaT:
        """Convert ORM to Pydantic."""
        return self.schema_class.model_validate(orm_obj)
