from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from pydantic import BaseModel, Field, ConfigDict

if TYPE_CHECKING:
    from store.common.storage import StorageService

from cl_ml_tools.plugins.face_detection.schema import BBox, FaceLandmarks

from store.common.schemas import Item



# Processing and Entity schemas
class JobSubmissionStatus(BaseModel):
    """Status of job submissions for an entity (return value)."""
    face_detection_job_id: str | None = None
    clip_job_id: str | None = None
    dino_job_id: str | None = None


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
    transaction_id: int | None = None
    
    model_config = ConfigDict(from_attributes=True)  # Allow creation from ORM objects

    def get_file_path(self, storage_service: StorageService) -> Path:
        """Resolve absolute file path using storage service.

        Args:
            storage_service: StorageService instance configured with media_dir

        Returns:
            Absolute Path to the file
        """
        if not self.file_path:
            raise ValueError(f"Entity {self.id} has no file_path")
        return storage_service.get_absolute_path(self.file_path)


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


class FaceResponse(BaseModel):
    """Response schema for detected face."""

    id: int = Field(..., description="Face ID")
    image_id: int = Field(..., description="Image ID this face belongs to")
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
    image_id: int = Field(..., description="Image ID")
    job_id: str = Field(..., description="Compute service job ID")
    task_type: str = Field(..., description="Task type (face_detection or clip_embedding)")
    status: str = Field(..., description="Job status (queued, in_progress, completed, failed)")
    created_at: int = Field(..., description="Creation timestamp (milliseconds)")
    updated_at: int = Field(..., description="Last update timestamp (milliseconds)")
    completed_at: int | None = Field(None, description="Completion timestamp (milliseconds)")
    error_message: str | None = Field(None, description="Error message if failed")


class SimilarImageResult(BaseModel):
    """Response schema for similar image search result."""

    image_id: int = Field(..., description="Image Entity ID")
    score: float = Field(..., description="Similarity score (0-1)")
    entity: Item | None = Field(None, description="Entity details if requested")


class SimilarImagesResponse(BaseModel):
    """Response schema for similar images search."""

    query_image_id: int = Field(..., description="Query Image Entity ID")
    results: list[SimilarImageResult] = Field(..., description="List of similar images")


class SimilarImageDinoResult(BaseModel):
    """Response schema for similar image search result using DINO."""

    image_id: int = Field(..., description="Image Entity ID")
    score: float = Field(..., description="Similarity score (0-1)")


class SimilarImagesDinoResponse(BaseModel):
    """Response schema for similar images search using DINO."""

    query_image_id: int = Field(..., description="Query Image Entity ID")
    results: list[SimilarImageDinoResult] = Field(..., description="List of similar images")


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
