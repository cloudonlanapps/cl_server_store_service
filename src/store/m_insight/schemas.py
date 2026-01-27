from pydantic import BaseModel, Field

from store.broadcast_service.schemas import (
    MInsightStatus as MInsightStatus,
    EntityStatusPayload as EntityStatusPayload,
)
from store.db_service.schemas import (
    EntityVersionSchema as EntityVersionSchema,
    FaceSchema as FaceSchema,
    KnownPersonSchema as KnownPersonSchema,
)
from store.vectorstore_services.schemas import SearchResult as SearchResult

# Processing and Entity schemas
class JobSubmissionStatus(BaseModel):
    """Status of job submissions for an entity (return value)."""

    face_detection_job_id: str | None = None
    clip_job_id: str | None = None
    dino_job_id: str | None = None



class UpdatePersonNameRequest(BaseModel):
    """Request schema for updating person name."""

    name: str = Field(..., min_length=1, max_length=255, description="Person name")


