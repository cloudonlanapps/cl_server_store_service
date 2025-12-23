from __future__ import annotations

from typing import Optional, cast

# Import shared models to ensure they're registered with our Base
from cl_server_shared.models import Job, QueueEntry
from sqlalchemy import BigInteger, Boolean, Float, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column

# Import Base from local database module (with WAL mode support)
from .database import Base

# Register shared model tables with our local Base metadata so alembic can find them
# This ensures the jobs and queue tables are created in our database
for table in [cast(Table, Job.__table__), cast(Table, QueueEntry.__table__)]:
    table.to_metadata(Base.metadata)


class Entity(Base):
    """SQLAlchemy model for media entities."""

    __tablename__ = "entities"
    __versioned__ = {}  # Enable SQLAlchemy-Continuum versioning

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Core fields
    is_collection: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Timestamps
    added_date: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_date: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    create_date: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # User identity tracking
    added_by: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)

    # File metadata
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String, nullable=True)
    type: Mapped[str | None] = mapped_column(String, nullable=True)
    extension: Mapped[str | None] = mapped_column(String, nullable=True)
    md5: Mapped[str | None] = mapped_column(String, unique=True, index=True, nullable=True)

    # File storage
    file_path: Mapped[str | None] = mapped_column(String, nullable=True)

    # Soft delete flag
    is_deleted: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)

    def __repr__(self) -> str:
        return f"<Entity(id={self.id}, label={self.label})>"


class ServiceConfig(Base):
    """SQLAlchemy model for service configuration."""

    __tablename__ = "service_config"

    # Primary key
    key: Mapped[str] = mapped_column(String, primary_key=True)

    # Configuration value (stored as string, parsed as needed)
    value: Mapped[str] = mapped_column(String, nullable=False)

    # Metadata
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)

    def __repr__(self) -> str:
        return f"<ServiceConfig(key={self.key}, value={self.value})>"


# Job and QueueEntry are imported from cl_server_shared above
