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
# Using absolute import to avoid circular dependency
import store.common.versioning as _versioning  # noqa: F401  # pyright: ignore[reportUnusedImport]

if TYPE_CHECKING:
    from .storage import StorageService


class Base(DeclarativeBase):
    """Base class for Store service models."""

    pass


class Entity(Base):
    """SQLAlchemy model for media entities."""

    __tablename__ = "entities"  # pyright: ignore[reportUnannotatedClassAttribute]
    __versioned__ = {}  # Enable SQLAlchemy-Continuum versioning  # pyright: ignore[reportUnannotatedClassAttribute]

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


class ImageIntelligence(Base):
    """Stores intelligence metadata for each image entity.

    One row per image, tracking md5, processing status, image path, and version.
    Cascade deletes when parent entity is deleted.
    """

    __tablename__ = "image_intelligence"  # pyright: ignore[reportUnannotatedClassAttribute]

    entity_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("entities.id", ondelete="CASCADE"),
        primary_key=True,
    )
    md5: Mapped[str] = mapped_column(Text, nullable=False)

    # Overall processing status
    # pending, processing, completed, failed
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")

    # Processing Status for individual steps logic is managed via EntityJob usually,
    # but here we also track job IDs.

    # Job tracking fields
    face_detection_job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    clip_job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    dino_job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    face_embedding_job_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # Re-using status field as 'processing_status' from plan,
    # but keeping name 'status' as it was before, unless I should rename it?
    # Plan says: processing_status: Mapped[str] = mapped_column(String, default="pending")
    # Existing was: status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    # I will add processing_status as a NEW field to match plan exactly and maybe migrate 'status' later or just use 'status'.
    # The plan shows:
    # processing_status: Mapped[str] = mapped_column(String, default="pending")
    # And it showed status as existing.
    # Actually, let's look at the plan again.
    # Plan: update trigger_async_jobs to update ImageIntelligence with job IDs.
    # Plan Section 5.1:
    # processing_status: Mapped[str] = mapped_column(String, default="pending")
    # existing 'status' was there.
    # I'll stick to 'processing_status' as requested in plan to avoid confusion,
    # but I might need to check if 'status' is used elsewhere.
    # The existing 'status' was 88: status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    # I will add processing_status.

    processing_status: Mapped[str] = mapped_column(String, default="pending")

    image_path: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationship to Entity
    image: Mapped[Entity] = relationship("Entity", back_populates="intelligence")

    @override
    def __repr__(self) -> str:
        return f"<ImageIntelligence(entity_id={self.entity_id}, md5={self.md5}, status={self.status}, processing_status={self.processing_status})>"


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


class EntityJob(Base):
    """Relationship table connecting entities to compute jobs."""

    __tablename__ = "entity_jobs"  # pyright: ignore[reportUnannotatedClassAttribute]

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to Image (Entity)
    entity_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Job tracking
    job_id: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    task_type: Mapped[str] = mapped_column(
        String, nullable=False
    )  # "face_detection" or "clip_embedding"
    status: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # "queued", "in_progress", "completed", "failed"

    # Timestamps (in milliseconds)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    completed_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Error tracking
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationship to Image (Entity)
    image: Mapped[Entity] = relationship("Entity", back_populates="jobs")

    @override
    def __repr__(self) -> str:
        return f"<EntityJob(id={self.id}, job_id={self.job_id}, task_type={self.task_type}, status={self.status})>"


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


class FaceMatch(Base):
    """Track face similarity matches for audit and debugging."""

    __tablename__ = "face_matches"  # pyright: ignore[reportUnannotatedClassAttribute]

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign keys to Face table
    face_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("faces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    matched_face_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("faces.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Similarity score (0.0-1.0)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)

    # Timestamp (in milliseconds)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)

    @override
    def __repr__(self) -> str:
        return f"<FaceMatch(id={self.id}, face_id={self.face_id}, matched_face_id={self.matched_face_id}, score={self.similarity_score:.3f})>"
