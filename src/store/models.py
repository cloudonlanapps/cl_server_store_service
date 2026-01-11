from __future__ import annotations

from typing import TYPE_CHECKING, override

# Import shared Base
from cl_server_shared.models import Base
from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Integer, String, Text
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

    # Relationships
    faces: Mapped[list["Face"]] = relationship("Face", back_populates="entity", cascade="all, delete-orphan")
    jobs: Mapped[list["EntityJob"]] = relationship("EntityJob", back_populates="entity", cascade="all, delete-orphan")

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


class Face(Base):
    """SQLAlchemy model for detected faces."""

    __tablename__ = "faces"  # pyright: ignore[reportUnannotatedClassAttribute]
    # __versioned__ = {}  # Enable SQLAlchemy-Continuum versioning for audit trail  # pyright: ignore[reportUnannotatedClassAttribute]  # Temporarily disabled to fix transaction issues

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to Entity
    entity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
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
    entity: Mapped[Entity] = relationship("Entity", back_populates="faces")
    known_person: Mapped[KnownPerson | None] = relationship("KnownPerson", back_populates="faces")

    # SQLAlchemy-Continuum adds this relationship dynamically
    if TYPE_CHECKING:
        from typing import Any  # pyright: ignore[reportUnannotatedClassAttribute]

        versions: VersionsRelationship[Any]  # pyright: ignore[reportExplicitAny, reportUninitializedInstanceVariable]

    @override
    def __repr__(self) -> str:
        return f"<Face(id={self.id}, entity_id={self.entity_id}, confidence={self.confidence})>"


class EntityJob(Base):
    """Relationship table connecting entities to compute jobs."""

    __tablename__ = "entity_jobs"  # pyright: ignore[reportUnannotatedClassAttribute]
    # Note: NO versioning for this table (it's operational, not domain data)

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to Entity
    entity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Job tracking
    job_id: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    task_type: Mapped[str] = mapped_column(String, nullable=False)  # "face_detection" or "clip_embedding"
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)  # "queued", "in_progress", "completed", "failed"

    # Timestamps (in milliseconds)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    completed_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Error tracking
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationship to Entity
    entity: Mapped[Entity] = relationship("Entity", back_populates="jobs")

    @override
    def __repr__(self) -> str:
        return f"<EntityJob(id={self.id}, job_id={self.job_id}, task_type={self.task_type}, status={self.status})>"


class KnownPerson(Base):
    """Person identified by face embeddings."""

    __tablename__ = "known_persons"  # pyright: ignore[reportUnannotatedClassAttribute]
    __versioned__ = {}  # Enable SQLAlchemy-Continuum versioning  # pyright: ignore[reportUnannotatedClassAttribute]

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # User-provided name (optional, can be set later)
    name: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    # Timestamps (in milliseconds)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Relationship to Face
    faces: Mapped[list[Face]] = relationship("Face", back_populates="known_person")

    # SQLAlchemy-Continuum adds this relationship dynamically
    if TYPE_CHECKING:
        from typing import Any  # pyright: ignore[reportUnannotatedClassAttribute]

        versions: VersionsRelationship[Any]  # pyright: ignore[reportExplicitAny, reportUninitializedInstanceVariable]

    @override
    def __repr__(self) -> str:
        return f"<KnownPerson(id={self.id}, name={self.name})>"


class FaceMatch(Base):
    """Track face similarity matches for audit and debugging."""

    __tablename__ = "face_matches"  # pyright: ignore[reportUnannotatedClassAttribute]
    # Note: NO versioning for this table (it's operational, not domain data)

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


# Job and QueueEntry are imported from cl_server_shared above
