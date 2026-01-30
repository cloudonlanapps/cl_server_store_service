from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, override

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)

# Import shared Base
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# CRITICAL: Import versioning BEFORE defining models with __versioned__
from . import versioning as _versioning  # noqa: F401  # pyright: ignore[reportUnusedImport]

if TYPE_CHECKING:
    from ..common.storage import StorageService


class Base(DeclarativeBase):
    """Base class for Store service models."""

    pass


class Entity(Base):
    """SQLAlchemy model for media entities."""

    __tablename__ = "entities"  # pyright: ignore[reportUnannotatedClassAttribute]
    __versioned__ = {}  # Enable SQLAlchemy-Continuum versioning  # pyright: ignore[reportUnannotatedClassAttribute]
    __table_args__ = {"sqlite_autoincrement": True}

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Core fields
    is_collection: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
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
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Intelligence (Denormalized)
    intelligence_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    faces: Mapped[list[Face]] = relationship(
        "Face", back_populates="image", cascade="all, delete-orphan"
    )

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


class EntitySyncState(Base):
    """Tracks the last processed Entity version for m_insight reconciliation.

    This is a singleton table with only one row (id=1).
    """

    __tablename__ = "entity_sync_state"  # pyright: ignore[reportUnannotatedClassAttribute]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    @override
    def __repr__(self) -> str:
        return f"<EntitySyncState(id={self.id}, last_version={self.last_version})>"




class Face(Base):
    """SQLAlchemy model for detected faces."""

    __tablename__ = "faces"  # pyright: ignore[reportUnannotatedClassAttribute]

    # Primary key (derived from entity_id and face index)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Foreign key to Image (Entity)
    entity_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Bounding box as JSON list [x1, y1, x2, y2] (normalized [0.0, 1.0])
    bbox: Mapped[str] = mapped_column(Text, nullable=False)

    # Detection confidence score
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    # Landmarks as JSON list [[x1, y1], [x2, y2], ...] (5 keypoints)
    landmarks: Mapped[str] = mapped_column(Text, nullable=False)

    # Path to cropped face image file
    file_path: Mapped[str] = mapped_column(String, nullable=False)

    # Timestamp in milliseconds
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Link to known person (identified by face recognition)
    known_person_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("known_persons.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Relationships
    image: Mapped[Entity] = relationship("Entity", back_populates="faces")
    known_person: Mapped[KnownPerson | None] = relationship("KnownPerson", back_populates="faces")

    @override
    def __repr__(self) -> str:
        return f"<Face(id={self.id}, entity_id={self.entity_id}, confidence={self.confidence})>"

    def get_file_path(self, storage_service: StorageService) -> Path:
        """Resolve absolute file path using storage service.

        Args:
            storage_service: StorageService instance configured with media_dir

        Returns:
            Absolute Path to the face image file
        """
        if not self.file_path:
            raise ValueError(f"Face {self.id} has no file_path")
        return storage_service.get_absolute_path(self.file_path)




class KnownPerson(Base):
    """Person identified by face embeddings."""

    __tablename__ = "known_persons"  # pyright: ignore[reportUnannotatedClassAttribute]
    __versioned__ = {}  # Enable SQLAlchemy-Continuum versioning # pyright: ignore[reportUnannotatedClassAttribute]

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # User-provided name (optional, can be set later)
    name: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    # Timestamps (in milliseconds)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Relationship to Face
    faces: Mapped[list[Face]] = relationship("Face", back_populates="known_person")

    @override
    def __repr__(self) -> str:
        return f"<KnownPerson(id={self.id}, name={self.name})>"

