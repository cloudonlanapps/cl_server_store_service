from __future__ import annotations

from pydantic import BaseModel, Field


class MInsightStatus(BaseModel):
    """Unified status information for a monitored MInsight process."""

    status: str = Field(..., description="Process status (unknown, running, idle, offline)")
    timestamp: int = Field(..., description="Event timestamp (milliseconds)")
    version_start: int | None = Field(default=None, description="Start version for current/last job")
    version_end: int | None = Field(default=None, description="End version for current/last job")
    processed_count: int | None = Field(default=None, description="Items processed in last job")


class EntityStatusPayload(BaseModel):
    """Payload for entity status broadcast."""

    entity_id: int = Field(..., description="Entity ID")
    status: str = Field(..., description="Overall status (queued, processing, completed, failed)")
    timestamp: int = Field(..., description="Timestamp (milliseconds)")

    # Flattened details
    face_detection: str | None = Field(default=None, description="Status of face detection")
    face_count: int | None = Field(
        default=None, description="Number of faces detected (if completed)"
    )
    clip_embedding: str | None = Field(default=None, description="Status of CLIP embedding")
    dino_embedding: str | None = Field(default=None, description="Status of DINO embedding")
    face_embeddings: list[str] | None = Field(
        default=None, description="List of face embedding statuses"
    )
