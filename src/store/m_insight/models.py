from __future__ import annotations

from typing import TYPE_CHECKING, override

from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..common.models import Base, Entity


class EntityVersionData(BaseModel):
    """Pydantic model for Entity version data from SQLAlchemy-Continuum.
    
    This represents all fields from an Entity version record,
    matching the Item schema for use in mInsight processing.
    """
    
    # Primary key
    id: int
    
    # Core fields
    is_collection: bool | None = None
    label: str | None = None
    description: str | None = None
    parent_id: int | None = None
    
    # Timestamps
    added_date: int | None = None
    updated_date: int | None = None
    create_date: int | None = None
    
    # User tracking
    added_by: str | None = None
    updated_by: str | None = None
    
    # File metadata
    file_size: int | None = None
    height: int | None = None
    width: int | None = None
    duration: float | None = None
    mime_type: str | None = None
    type: str | None = None
    extension: str | None = None
    md5: str | None = None
    file_path: str | None = None
    
    # Soft delete
    is_deleted: bool | None = None
    
    # Version tracking (from SQLAlchemy-Continuum)
    transaction_id: int
    
    model_config = ConfigDict(from_attributes=True)  # Allow creation from ORM objects


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

    image_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("entities.id", ondelete="CASCADE"),
        primary_key=True,
    )
    md5: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    image_path: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationship to Entity
    image: Mapped[Entity] = relationship("Entity", back_populates="intelligence")

    @override
    def __repr__(self) -> str:
        return f"<ImageIntelligence(image_id={self.image_id}, md5={self.md5}, status={self.status}, version={self.version})>"


class Face(Base):
    """SQLAlchemy model for detected faces."""

    __tablename__ = "faces"  # pyright: ignore[reportUnannotatedClassAttribute]

    # Primary key (derived from image_id and face index)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Foreign key to Image (Entity)
    image_id: Mapped[int] = mapped_column(
        "entity_id", Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
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

    # SQLAlchemy-Continuum adds this relationship dynamically
    if TYPE_CHECKING:
        from typing import Any  # pyright: ignore[reportUnannotatedClassAttribute]

        from typings.sqlalchemy_continuum import VersionsRelationship

        versions: VersionsRelationship[Any]  # pyright: ignore[reportExplicitAny, reportUninitializedInstanceVariable]

    @override
    def __repr__(self) -> str:
        return f"<Face(id={self.id}, image_id={self.image_id}, confidence={self.confidence})>"


class EntityJob(Base):
    """Relationship table connecting entities to compute jobs."""

    __tablename__ = "entity_jobs"  # pyright: ignore[reportUnannotatedClassAttribute]
    # Note: NO versioning for this table (it's operational, not domain data)

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to Image (Entity)
    image_id: Mapped[int] = mapped_column(
        "entity_id", Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
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

        from typings.sqlalchemy_continuum import VersionsRelationship

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


class MInsightStartPayload(BaseModel):
    """Payload for mInsight/start topic."""
    
    version_start: int
    version_end: int
    timestamp: int


class MInsightStopPayload(BaseModel):
    """Payload for mInsight/stop topic."""
    
    processed_count: int
    timestamp: int


class MInsightStatusPayload(BaseModel):
    """Payload for mInsight status heartbeat."""
    
    status: str
    timestamp: int


__all__ = [
    "EntitySyncState", 
    "ImageIntelligence", 
    "EntityVersionData",
    "Face",
    "EntityJob",
    "KnownPerson",
    "FaceMatch",
    "MInsightStartPayload",
    "MInsightStopPayload",
    "MInsightStatusPayload",
]
