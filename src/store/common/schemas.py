from __future__ import annotations

from cl_ml_tools.plugins.face_detection.schema import BBox, FaceLandmarks
from pydantic import BaseModel, Field


class BodyCreateEntity(BaseModel):
    label: str | None = Field(None, title="Label")
    description: str | None = Field(None, title="Description")
    parent_id: int | None = Field(None, title="Parent Id")
    is_collection: bool = Field(..., title="Is Collection")
    # image is part of the multipart body – handled separately


class BodyUpdateEntity(BaseModel):
    label: str | None = Field(None, title="Label")
    description: str | None = Field(None, title="Description")
    parent_id: int | None = Field(None, title="Parent Id")
    is_collection: bool = Field(..., title="Is Collection")
    # image is part of the multipart body – handled separately


class BodyPatchEntity(BaseModel):
    label: str | None = Field(None, title="Label")
    description: str | None = Field(None, title="Description")
    parent_id: int | None = Field(None, title="Parent Id")
    is_deleted: bool | None = Field(None, title="Is Deleted")


class Item(BaseModel):
    id: int | None = Field(None, title="Id", json_schema_extra={"read_only": True})
    is_collection: bool | None = Field(None, title="Is Collection")
    label: str | None = Field(None, title="Label")
    description: str | None = Field(None, title="Description")
    parent_id: int | None = Field(None, title="Parent Id")
    added_date: int | None = Field(None, title="Added Date", json_schema_extra={"read_only": True})
    updated_date: int | None = Field(
        None, title="Updated Date", json_schema_extra={"read_only": True}
    )
    is_deleted: bool | None = Field(None, title="Is Deleted")
    create_date: int | None = Field(
        None, title="Create Date", json_schema_extra={"read_only": True}
    )
    added_by: str | None = Field(None, title="Added By", json_schema_extra={"read_only": True})
    updated_by: str | None = Field(None, title="Updated By", json_schema_extra={"read_only": True})
    file_size: int | None = Field(None, title="File Size", json_schema_extra={"read_only": True})
    height: int | None = Field(None, title="Height", json_schema_extra={"read_only": True})
    width: int | None = Field(None, title="Width", json_schema_extra={"read_only": True})
    duration: float | None = Field(None, title="Duration", json_schema_extra={"read_only": True})
    mime_type: str | None = Field(None, title="Mime Type", json_schema_extra={"read_only": True})
    type: str | None = Field(None, title="Type", json_schema_extra={"read_only": True})
    extension: str | None = Field(None, title="Extension", json_schema_extra={"read_only": True})
    md5: str | None = Field(None, title="Md5", json_schema_extra={"read_only": True})
    file_path: str | None = Field(None, title="File Path", json_schema_extra={"read_only": True})
    is_deleted: bool | None = Field(None, title="Is Deleted")
    is_indirectly_deleted: bool | None = Field(
        None,
        title="Is Indirectly Deleted",
        description="True if any ancestor in the parent chain is soft-deleted",
    )


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

    items: list[Item] = Field(..., description="List of items for the current page")
    pagination: PaginationMetadata = Field(..., description="Pagination metadata")


# Admin configuration schemas
class ConfigResponse(BaseModel):
    """Response schema for configuration."""

    guest_mode: bool = Field(
        ..., description="Whether guest mode is enabled (true = no authentication required)"
    )
    updated_at: int | None = Field(None, description="Last update timestamp (milliseconds)")
    updated_by: str | None = Field(None, description="User ID who last updated the config")


class UpdateReadAuthConfig(BaseModel):
    """Request schema for updating read auth configuration."""

    enabled: bool = Field(..., description="Whether to enable read authentication")


# Face detection and job schemas
class FaceResponse(BaseModel):
    """Response schema for detected face."""

    id: int = Field(..., description="Face ID")
    entity_id: int = Field(..., description="Entity ID this face belongs to")
    bbox: BBox = Field(
        ..., description="Normalized bounding box [x1, y1, x2, y2] in range [0.0, 1.0]"
    )
    confidence: float = Field(..., description="Detection confidence score [0.0, 1.0]")
    landmarks: FaceLandmarks = Field(
        ..., description="Five facial keypoints [[x1, y1], [x2, y2], ...]"
    )
    file_path: str = Field(..., description="Relative path to cropped face image")
    created_at: int = Field(..., description="Creation timestamp (milliseconds)")
    known_person_id: int | None = Field(None, description="Known person ID (face recognition)")


class EntityJobResponse(BaseModel):
    """Response schema for entity job status."""

    id: int = Field(..., description="Job record ID")
    entity_id: int = Field(..., description="Entity ID")
    job_id: str = Field(..., description="Compute service job ID")
    task_type: str = Field(..., description="Task type (face_detection or clip_embedding)")
    status: str = Field(..., description="Job status (queued, in_progress, completed, failed)")
    created_at: int = Field(..., description="Creation timestamp (milliseconds)")
    updated_at: int = Field(..., description="Last update timestamp (milliseconds)")
    completed_at: int | None = Field(None, description="Completion timestamp (milliseconds)")
    error_message: str | None = Field(None, description="Error message if failed")


class SimilarImageResult(BaseModel):
    """Response schema for similar image search result."""

    entity_id: int = Field(..., description="Entity ID of similar image")
    score: float = Field(..., description="Similarity score [0.0, 1.0]")
    entity: Item | None = Field(None, description="Entity details (optional)")


class SimilarImagesResponse(BaseModel):
    """Response schema for similar image search."""

    results: list[SimilarImageResult] = Field(..., description="List of similar images")
    query_entity_id: int = Field(..., description="Query entity ID")


# KnownPerson (face recognition) schemas
class KnownPersonResponse(BaseModel):
    """Response schema for known person."""

    id: int = Field(..., description="Known person ID")
    name: str | None = Field(None, description="Person name (optional)")
    created_at: int = Field(..., description="Creation timestamp (milliseconds)")
    updated_at: int = Field(..., description="Last update timestamp (milliseconds)")
    face_count: int | None = Field(None, description="Number of faces for this person (optional)")


class UpdatePersonNameRequest(BaseModel):
    """Request schema for updating person name."""

    name: str = Field(..., min_length=1, max_length=255, description="Person name")


class FaceMatchResult(BaseModel):
    """Response schema for face match."""

    id: int = Field(..., description="Match record ID")
    face_id: int = Field(..., description="Source face ID")
    matched_face_id: int = Field(..., description="Matched face ID")
    similarity_score: float = Field(..., description="Similarity score [0.0, 1.0]")
    created_at: int = Field(..., description="Match timestamp (milliseconds)")
    matched_face: FaceResponse | None = Field(None, description="Matched face details (optional)")


class SimilarFacesResult(BaseModel):
    """Response schema for similar face search result."""

    face_id: int = Field(..., description="Face ID")
    score: float = Field(..., description="Similarity score [0.0, 1.0]")
    known_person_id: int | None = Field(None, description="Known person ID")
    face: FaceResponse | None = Field(None, description="Face details (optional)")


class SimilarFacesResponse(BaseModel):
    """Response schema for similar face search."""

    results: list[SimilarFacesResult] = Field(..., description="List of similar faces")
    query_face_id: int = Field(..., description="Query face ID")
