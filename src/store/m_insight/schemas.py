from __future__ import annotations

from pathlib import Path

import numpy as np
from cl_ml_tools.plugins.face_detection.schema import BBox, FaceLandmarks
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field
from qdrant_client.http.models.models import Payload
from qdrant_client.models import StrictInt

from store.common.schemas import (
    Item as Item,
    MInsightStatus as MInsightStatus,
)
from store.common.storage import StorageService
from store.db_service.schemas import (
    EntityVersionSchema,
    FaceSchema,
    KnownPersonSchema,
)

# Processing and Entity schemas
class JobSubmissionStatus(BaseModel):
    """Status of job submissions for an entity (return value)."""

    face_detection_job_id: str | None = None
    clip_job_id: str | None = None
    dino_job_id: str | None = None


class EntityStatusDetails(BaseModel):
    """Detailed status breakdown for entity processing."""
    face_detection: str | None = Field(default=None, description="Status of face detection")
    face_count: int | None = Field(default=None, description="Number of faces detected (if completed)")
    clip_embedding: str | None = Field(default=None, description="Status of CLIP embedding")
    dino_embedding: str | None = Field(default=None, description="Status of DINO embedding")
    face_embeddings: list[str] | None = Field(default=None, description="List of face embedding statuses")


class EntityStatusPayload(BaseModel):
    """Payload for entity status broadcast."""

    entity_id: int = Field(..., description="Entity ID")
    status: str = Field(..., description="Overall status (queued, processing, completed, failed)")
    details: EntityStatusDetails = Field(
        default_factory=lambda: EntityStatusDetails(),
        description="Detailed status breakdown",
    )
    timestamp: int = Field(..., description="Timestamp (milliseconds)")


class SimilarImageResult(BaseModel):
    """Response schema for similar image search result."""

    entity_id: int = Field(..., description="Image Entity ID")
    score: float = Field(..., description="Similarity score (0-1)")
    entity: Item | None = Field(None, description="Entity details if requested")


class SimilarImagesResponse(BaseModel):
    """Response schema for similar images search."""

    query_entity_id: int = Field(..., description="Query Image Entity ID")
    results: list[SimilarImageResult] = Field(..., description="List of similar images")


class SimilarImageDinoResult(BaseModel):
    """Response schema for similar image search result using DINO."""

    entity_id: int = Field(..., description="Image Entity ID")
    score: float = Field(..., description="Similarity score (0-1)")


class SimilarImagesDinoResponse(BaseModel):
    """Response schema for similar images search using DINO."""

    query_entity_id: int = Field(..., description="Query Image Entity ID")
    results: list[SimilarImageDinoResult] = Field(..., description="List of similar images")


class UpdatePersonNameRequest(BaseModel):
    """Request schema for updating person name."""

    name: str = Field(..., min_length=1, max_length=255, description="Person name")


class SimilarFacesResult(BaseModel):
    """Response schema for similar face search result."""

    face_id: int = Field(..., description="Face ID")
    score: float = Field(..., description="Similarity score [0.0, 1.0]")
    known_person_id: int | None = Field(None, description="Known person ID")
    face: FaceSchema | None = Field(None, description="Face details (optional)")


class SimilarFacesResponse(BaseModel):
    """Response schema for similar face search."""

    results: list[SimilarFacesResult] = Field(..., description="List of similar faces")
    query_face_id: int = Field(..., description="Query face ID")


class StoreItem(BaseModel):
    model_config: ConfigDict = ConfigDict(arbitrary_types_allowed=True)  # pyright: ignore[reportIncompatibleVariableOverride]
    id: StrictInt
    embedding: NDArray[np.float32]
    payload: Payload | None


class SearchPreferences(BaseModel):
    with_payload: bool = True
    with_vectors: bool = True
    score_threshold: float = 0.85


class SearchResult(BaseModel):
    model_config: ConfigDict = ConfigDict(arbitrary_types_allowed=True)  # pyright: ignore[reportIncompatibleVariableOverride]
    id: int
    embedding: NDArray[np.float32]
    score: float
    payload: Payload | None
