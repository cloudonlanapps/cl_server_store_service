from __future__ import annotations

from typing import TYPE_CHECKING, override

# Import shared Base
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """Base class for Store service models."""
    pass
from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

# CRITICAL: Import versioning BEFORE defining models with __versioned__
from . import versioning  # noqa: F401  # pyright: ignore[reportUnusedImport]

if TYPE_CHECKING:
    from typings.sqlalchemy_continuum import VersionsRelationship


class Entity(Base):
    """SQLAlchemy model for media entities."""

    __tablename__ = "entities"  # pyright: ignore[reportUnannotatedClassAttribute]
    __versioned__ = {}  # Enable SQLAlchemy-Continuum versioning  # pyright: ignore[reportUnannotatedClassAttribute]

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Core fields
    is_collection: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("entities.id"), nullable=True, index=True
    )

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

    # Intelligence Relationships
    faces: Mapped[list[Face]] = relationship(
        "Face", back_populates="image", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[EntityJob]] = relationship(
        "EntityJob", back_populates="image", cascade="all, delete-orphan"
    )
    intelligence: Mapped[ImageIntelligence | None] = relationship(
        "ImageIntelligence", back_populates="image", uselist=False, cascade="all, delete-orphan"
    )

    # SQLAlchemy-Continuum adds this relationship dynamically
    if TYPE_CHECKING:
        from typing import Any  # pyright: ignore[reportUnannotatedClassAttribute]

        versions: VersionsRelationship[Any]  # pyright: ignore[reportExplicitAny, reportUninitializedInstanceVariable]

    @override
    def __repr__(self) -> str:
        return f"<Entity(id={self.id}, label={self.label})>"


class ServiceConfig(Base):
    """SQLAlchemy model for service configuration."""

    __tablename__ = "service_config"  # pyright: ignore[reportUnannotatedClassAttribute]

    # Primary key
    key: Mapped[str] = mapped_column(String, primary_key=True)

    # Configuration value (stored as string, parsed as needed)
    value: Mapped[str] = mapped_column(String, nullable=False)

    # Metadata
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)

    @override
    def __repr__(self) -> str:
        return f"<ServiceConfig(key={self.key}, value={self.value})>"


# Import intelligence models to ensure they are registered with Base for Alembic
# These are imported at runtime after all models are defined
# The relationship() uses string references, so circular imports work for ORM

if TYPE_CHECKING:
    from ..m_insight.models import ImageIntelligence
    from ..m_insight.models import EntityJob, Face, FaceMatch, KnownPerson

# Runtime import happens when these modules are imported elsewhere
# (e.g., via alembic or when the full application starts)
