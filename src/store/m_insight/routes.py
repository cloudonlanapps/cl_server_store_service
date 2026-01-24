from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Response

from store.common.auth import UserPayload, require_permission
from store.db_service.schemas import EntityJobSchema
from . import schemas as intel_schemas
from .dependencies import get_intelligence_service
from .retrieval_service import IntelligenceRetrieveService, ResourceNotFoundError

router = APIRouter(tags=["intelligence"])


@router.get(
    "/entities/{entity_id}/faces",
    tags=["entity", "face-detection"],
    summary="Get Entity Faces",
    description="Retrieves all detected faces for a specific entity.",
    operation_id="get_entity_faces",
)
async def get_entity_faces(
    entity_id: int = Path(..., title="Entity Id"),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
    service: IntelligenceRetrieveService = Depends(get_intelligence_service),
) -> list[intel_schemas.FaceSchema]:
    """Get all faces detected in an entity."""
    _ = user

    try:
        return service.get_entity_faces(entity_id)
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Entity not found")


@router.get(
    "/faces/{face_id}/embedding",
    tags=["face-detection"],
    summary="Download Face Embedding",
    description="Downloads the face embedding vector from Qdrant as a .npy file.",
    operation_id="download_face_embedding",
)
async def download_face_embedding(
    face_id: int = Path(..., title="Face Id"),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
    service: IntelligenceRetrieveService = Depends(get_intelligence_service),
):
    """Download face embedding from Qdrant vector store."""
    _ = user

    try:
        buffer = service.get_face_embedding_buffer(face_id)
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Face or embedding not found in vector store")

    return Response(
        content=buffer.getvalue(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename=face_{face_id}_embedding.npy"},
    )


@router.get(
    "/entities/{entity_id}/clip_embedding",
    tags=["entity", "clip-embedding"],
    summary="Download Entity CLIP Embedding",
    description="Downloads the CLIP image embedding vector from Qdrant as a .npy file.",
    operation_id="download_entity_clip_embedding",
)
async def download_entity_clip_embedding(
    entity_id: int = Path(..., title="Entity Id"),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
    service: IntelligenceRetrieveService = Depends(get_intelligence_service),
):
    """Download entity CLIP embedding from Qdrant vector store."""
    _ = user

    try:
        buffer = service.get_clip_embedding_buffer(entity_id)
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Entity or embedding not found in vector store")

    return Response(
        content=buffer.getvalue(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename=entity_{entity_id}_clip_embedding.npy"
        },
    )


@router.get(
    "/entities/{entity_id}/dino_embedding",
    tags=["entity", "dino-embedding"],
    summary="Download Entity DINO Embedding",
    description="Downloads the DINO image embedding vector from Qdrant as a .npy file.",
    operation_id="download_entity_dino_embedding",
)
async def download_entity_dino_embedding(
    entity_id: int = Path(..., title="Entity Id"),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
    service: IntelligenceRetrieveService = Depends(get_intelligence_service),
):
    """Download entity DINO embedding from Qdrant vector store."""
    _ = user

    try:
        buffer = service.get_dino_embedding_buffer(entity_id)
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Entity or embedding not found in vector store")

    return Response(
        content=buffer.getvalue(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename=entity_{entity_id}_dino_embedding.npy"
        },
    )


@router.get(
    "/entities/{entity_id}/jobs",
    tags=["entity", "jobs"],
    summary="Get Entity Jobs",
    description="Retrieves job status for all compute jobs associated with an entity.",
    operation_id="get_entity_jobs",
)
async def get_entity_jobs(
    entity_id: int = Path(..., title="Entity Id"),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
    service: IntelligenceRetrieveService = Depends(get_intelligence_service),
) -> list[EntityJobSchema]:
    """Get all jobs for an entity."""
    _ = user

    try:
        return service.get_entity_jobs(entity_id)
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Entity not found")


@router.get(
    "/entities/{entity_id}/similar",
    tags=["entity", "search"],
    summary="Find Similar Images",
    description="Find similar images using CLIP embeddings. Requires the entity to have a CLIP embedding.",
    operation_id="find_similar_images",
)
async def find_similar_images(
    entity_id: int = Path(..., title="Entity Id"),
    limit: int = Query(5, ge=1, le=50, description="Maximum number of results"),
    score_threshold: float = Query(0.85, ge=0.0, le=1.0, description="Minimum similarity score"),
    include_details: bool = Query(False, description="Include entity details in results"),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
    service: IntelligenceRetrieveService = Depends(get_intelligence_service),
) -> intel_schemas.SimilarImagesResponse:
    """Find similar images using CLIP embeddings."""
    _ = user

    try:
        results = service.search_similar_images(
            entity_id, limit, score_threshold, include_details=include_details
        )
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Entity not found")

    if not results:
        raise HTTPException(
            status_code=404,
            detail="No similar images found. Entity may not have an embedding yet.",
        )

    return intel_schemas.SimilarImagesResponse(
        results=results,
        query_entity_id=entity_id,
    )


@router.get(
    "/faces/{face_id}/similar",
    tags=["face-recognition"],
    summary="Find Similar Faces",
    description="Find similar faces using face embeddings. Requires the face to have an embedding.",
    operation_id="find_similar_faces",
)
async def find_similar_faces(
    face_id: int = Path(..., title="Face Id"),
    limit: int = Query(5, ge=1, le=50, description="Maximum number of results"),
    threshold: float = Query(0.7, ge=0.0, le=1.0, description="Minimum similarity score"),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
    service: IntelligenceRetrieveService = Depends(get_intelligence_service),
) -> intel_schemas.SimilarFacesResponse:
    """Find similar faces using face embeddings."""
    _ = user

    try:
        results = service.search_similar_faces_by_id(face_id, limit, threshold)
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Face not found")

    if not results:
        raise HTTPException(
            status_code=404,
            detail="No similar faces found. Face may not have an embedding yet.",
        )

    return intel_schemas.SimilarFacesResponse(
        results=results,
        query_face_id=face_id,
    )




@router.get(
    "/known-persons",
    tags=["face-recognition"],
    summary="Get All Known Persons",
    description="Get all known persons (identified by face recognition).",
    operation_id="get_all_known_persons",
)
async def get_all_known_persons(
    user: UserPayload | None = Depends(require_permission("media_store_read")),
    service: IntelligenceRetrieveService = Depends(get_intelligence_service),
) -> list[intel_schemas.KnownPersonSchema]:
    """Get all known persons."""
    _ = user
    return service.get_all_known_persons()


@router.get(
    "/known-persons/{person_id}",
    tags=["face-recognition"],
    summary="Get Known Person",
    description="Get details of a specific known person.",
    operation_id="get_known_person",
)
async def get_known_person(
    person_id: int = Path(..., title="Person Id"),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
    service: IntelligenceRetrieveService = Depends(get_intelligence_service),
) -> intel_schemas.KnownPersonSchema:
    """Get known person details."""
    _ = user

    person = service.get_known_person(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Known person not found")

    return person


@router.get(
    "/known-persons/{person_id}/faces",
    tags=["face-recognition"],
    summary="Get Person Faces",
    description="Get all faces for a specific known person.",
    operation_id="get_person_faces",
)
async def get_person_faces(
    person_id: int = Path(..., title="Person Id"),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
    service: IntelligenceRetrieveService = Depends(get_intelligence_service),
) -> list[intel_schemas.FaceSchema]:
    """Get all faces for a known person."""
    _ = user

    try:
        return service.get_known_person_faces(person_id)
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Known person not found")


@router.patch(
    "/known-persons/{person_id}",
    tags=["face-recognition"],
    summary="Update Person Name",
    description="Update the name of a known person.",
    operation_id="update_person_name",
)
async def update_person_name(
    person_id: int = Path(..., title="Person Id"),
    body: intel_schemas.UpdatePersonNameRequest = Body(...),
    user: UserPayload | None = Depends(require_permission("media_store_write")),
    service: IntelligenceRetrieveService = Depends(get_intelligence_service),
) -> intel_schemas.KnownPersonSchema:
    """Update person name."""
    _ = user

    result = service.update_known_person_name(person_id, body.name)
    if not result:
        raise HTTPException(status_code=404, detail="Known person not found")

    return result
