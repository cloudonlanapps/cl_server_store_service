
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