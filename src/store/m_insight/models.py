"""SQLAlchemy models for m_insight intelligence tracking.

This module defines:
- EntitySyncState: Singleton table tracking last processed Entity version
- ImageIntelligence: Per-image intelligence metadata with md5 and status
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from pydantic import BaseModel, ConfigDict
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..common.models import Base


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

    if TYPE_CHECKING:
        from ..common.models import Entity

    @override
    def __repr__(self) -> str:
        return f"<ImageIntelligence(image_id={self.image_id}, md5={self.md5}, status={self.status}, version={self.version})>"



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
    "MInsightStartPayload",
    "MInsightStopPayload",
    "MInsightStatusPayload",
]
