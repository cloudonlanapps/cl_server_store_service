from __future__ import annotations

from typing import Annotated, Any, TYPE_CHECKING, ClassVar

from cl_ml_tools import BBox, FaceLandmarks
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def parse_bbox(v: Any) -> Any:
    """Parse BBox from JSON string if needed."""
    if isinstance(v, str):
        return BBox.model_validate_json(v)
    return v


def parse_landmarks(v: Any) -> Any:
    """Parse FaceLandmarks from JSON string if needed."""
    if isinstance(v, str):
        return FaceLandmarks.model_validate_json(v)
    return v


# Annotated types for handling JSON strings from DB
BBoxField = Annotated[BBox, BeforeValidator(parse_bbox)]
FaceLandmarksField = Annotated[FaceLandmarks, BeforeValidator(parse_landmarks)]


class EntitySchema(BaseModel):
    """Pydantic model for Entity."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    is_collection: bool = False
    label: str | None = None
    description: str | None = None
    parent_id: int | None = None

    added_date: int | None = None
    updated_date: int | None = None
    create_date: int | None = None

    added_by: str | None = None
    updated_by: str | None = None

    file_size: int | None = None
    height: int | None = None
    width: int | None = None
    duration: float | None = None
    mime_type: str | None = None
    type: str | None = None
    extension: str | None = None
    md5: str | None = None
    file_path: str | None = None
    is_deleted: bool = False
    is_indirectly_deleted: bool | None = Field(
        None, description="True if any ancestor in the parent chain is soft-deleted"
    )


class JobInfo(BaseModel):
    """Job tracking information."""

    job_id: str
    task_type: str  # clip_embedding, dino_embedding, face_detection, etc.
    started_at: int
    status: str = "queued"
    completed_at: int | None = None
    error_message: str | None = None


class InferenceStatus(BaseModel):
    """Fine-grained inference status."""

    face_detection: str = "pending"
    clip_embedding: str = "pending"
    dino_embedding: str = "pending"
    face_embeddings: list[str] | None = None  # Status for each face


class EntityIntelligenceData(BaseModel):
    """Pydantic model for denormalized intelligence data (JSON field)."""

    # Persistence
    overall_status: str = "queued"  # queued, processing, completed, failed
    last_processed_md5: str | None = None
    last_processed_version: int | None = None
    face_count: int | None = None

    # Safety for race conditions
    active_processing_md5: str | None = None

    # Job Tracking (Explicit List)
    active_jobs: list[JobInfo] = Field(default_factory=list)
    job_history: list[JobInfo] = Field(default_factory=list)

    # Fine-grained status for UI (Explicit Model)
    inference_status: InferenceStatus = Field(default_factory=InferenceStatus)

    # Timestamps / Errors
    last_updated: int
    error_message: str | None = None


class EntityVersionSchema(BaseModel):
    """Pydantic model for EntityVersion (read-only)."""

    model_config = ConfigDict(from_attributes=True)

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

    # Note: intelligence_data is excluded from versioning and not available in version records

    # Version tracking
    transaction_id: int | None = None
    operation_type: int | None = None  # 0: INSERT, 1: UPDATE, 2: DELETE




class FaceSchema(BaseModel):
    """Pydantic model for Face."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_id: int
    known_person_id: int | None = None
    bbox: BBoxField
    confidence: float
    landmarks: FaceLandmarksField
    file_path: str
    created_at: int


class KnownPersonSchema(BaseModel):
    """Pydantic model for KnownPerson."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None  # Optional for creation
    name: str | None = None
    created_at: int
    updated_at: int
    face_count: int | None = None


class EntitySyncStateSchema(BaseModel):
    """Pydantic model for EntitySyncState."""

    model_config = ConfigDict(from_attributes=True)

    id: int = 1
    last_version: int = 0


class ServiceConfigSchema(BaseModel):
    """Pydantic model for ServiceConfig."""

    model_config = ConfigDict(from_attributes=True)

    key: str
    value: str
    updated_at: int



class PaginationMetadata(BaseModel):
    """Pagination metadata for paginated responses."""

    page: int = Field(..., description="Current page number (1-indexed)")
    page_size: int = Field(..., description="Number of items per page")
    total_items: int = Field(..., description="Total number of items across all pages")
    total_pages: int = Field(..., description="Total number of pages")
    has_next: bool = Field(..., description="Whether there is a next page")
    has_prev: bool = Field(..., description="Whether there is a previous page")


class PaginatedResponse(BaseModel):
    """Paginated response wrapper for entity lists."""

    items: list[EntitySchema] = Field(..., description="List of items for the current page")
    pagination: PaginationMetadata = Field(..., description="Pagination metadata")


class ConfigResponse(BaseModel):
    """Response schema for configuration."""

    guest_mode: bool = Field(
        ..., description="Whether guest mode is enabled (true = no authentication required)"
    )
    updated_at: int | None = Field(None, description="Last update timestamp (milliseconds)")
    updated_by: str | None = Field(None, description="User ID who last updated the config")


class UpdateReadAuthConfig(BaseModel):
    """Request schema for updating read authentication configuration."""

    enabled: bool = Field(..., description="Whether to enable read authentication")


class VersionInfo(BaseModel):
    """Information about an entity version."""

    version: int = Field(..., description="Version number (1-indexed)")
    transaction_id: int | None = Field(None, description="Transaction ID of the version")
    updated_date: int | None = Field(None, description="Last update timestamp (milliseconds)")

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)
