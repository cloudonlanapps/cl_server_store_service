from __future__ import annotations

from typing import Annotated, Any, TYPE_CHECKING

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

    # Version tracking
    transaction_id: int | None = None
    operation_type: int | None = None  # 0: INSERT, 1: UPDATE, 2: DELETE


class ImageIntelligenceSchema(BaseModel):
    """Pydantic model for ImageIntelligence."""

    model_config = ConfigDict(from_attributes=True)

    entity_id: int
    md5: str
    status: str = "queued"
    processing_status: str = "pending"
    image_path: str
    version: int = 1

    face_detection_job_id: str | None = None
    clip_job_id: str | None = None
    dino_job_id: str | None = None
    face_embedding_job_ids: list[str] | None = None


class EntityJobSchema(BaseModel):
    """Pydantic model for EntityJob."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None  # Optional for creation
    entity_id: int
    job_id: str
    task_type: str
    status: str
    created_at: int
    updated_at: int
    completed_at: int | None = None
    error_message: str | None = None


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


class FaceMatchSchema(BaseModel):
    """Pydantic model for FaceMatch."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None  # Optional for creation
    face_id: int
    matched_face_id: int
    similarity_score: float
    created_at: int
    matched_face: FaceSchema | None = None


class EntitySyncStateSchema(BaseModel):
    """Pydantic model for EntitySyncState."""

    model_config = ConfigDict(from_attributes=True)

    id: int = 1
    last_version: int = 0
