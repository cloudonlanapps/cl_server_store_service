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
from store.vectorstore_services.schemas import SearchResult as SearchResult

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



class UpdatePersonNameRequest(BaseModel):
    """Request schema for updating person name."""

    name: str = Field(..., min_length=1, max_length=255, description="Person name")


