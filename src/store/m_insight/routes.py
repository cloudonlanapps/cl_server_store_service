from __future__ import annotations

from typing import cast
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Response

from store.common.auth import UserPayload, require_permission
from store.db_service.schemas import JobInfo, EntityIntelligenceData
from store.db_service import DBService
from store.db_service.exceptions import ResourceNotFoundError
from store.vectorstore_services.exceptions import VectorResourceNotFound
from . import schemas as intel_schemas
from .dependencies import (
    get_clip_store_dep,
    get_db_service,
    get_dino_store_dep,
    get_face_store_dep,
)
from store.vectorstore_services.vector_stores import QdrantVectorStore
from store.vectorstore_services.schemas import SearchPreferences

router = APIRouter(tags=["intelligence"])


@router.get(
    "/entities/{entity_id}",
    tags=["entity", "intelligence"],
    summary="Get Entity Intelligence Data",
    description="Retrieves intelligence data (processing status, jobs, etc.) for a specific entity.",
    operation_id="get_entity_intelligence",
)
async def get_entity_intelligence(
    entity_id: int = Path(..., title="Entity Id"),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
    db: DBService = Depends(get_db_service),
) -> EntityIntelligenceData | None:
    """Get intelligence data for an entity."""
    _ = user

    try:
        # Verify entity exists
        _ = db.entity.get_or_raise(entity_id)

        # Get intelligence data from separate table
        return db.intelligence.get_intelligence_data(entity_id)
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Entity not found")


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
    db: DBService = Depends(get_db_service),
) -> list[intel_schemas.FaceSchema]:
    """Get all faces detected in an entity."""
    _ = user

    try:
        _ = db.entity.get_or_raise(entity_id)
        return db.face.get_by_entity_id(entity_id)
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
    db: DBService = Depends(get_db_service),
    face_store: QdrantVectorStore = Depends(get_face_store_dep),
):
    """Download face embedding from Qdrant vector store."""
    _ = user

    try:
        _ = db.face.get_or_raise(face_id)
        buffer = face_store.get_vector_buffer(face_id)
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Face not found")
    except VectorResourceNotFound:
        raise HTTPException(status_code=404, detail="Face Vector not found")

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
    db: DBService = Depends(get_db_service),
    clip_store: QdrantVectorStore = Depends(get_clip_store_dep),
):
    """Download entity CLIP embedding from Qdrant vector store."""
    _ = user

    try:
        _ = db.entity.get_or_raise(entity_id)
        buffer = clip_store.get_vector_buffer(entity_id)
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Entity not found")
    except VectorResourceNotFound:
        raise HTTPException(status_code=404, detail="Entity CLIP Vector not found")

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
    db: DBService = Depends(get_db_service),
    dino_store: QdrantVectorStore = Depends(get_dino_store_dep),
):
    """Download entity DINO embedding from Qdrant vector store."""
    _ = user

    try:
        _ = db.entity.get_or_raise(entity_id)
        buffer = dino_store.get_vector_buffer(entity_id)
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Entity not found")
    except VectorResourceNotFound:
        raise HTTPException(status_code=404, detail="Entity DINO Vector not found")

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
    description="Retrieves active job information from denormalized intelligence data.",
    operation_id="get_entity_jobs",
)
async def get_entity_jobs(
    entity_id: int = Path(..., title="Entity Id"),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
    db: DBService = Depends(get_db_service),
) -> list[JobInfo]:
    """Get all active jobs for an entity."""
    _ = user

    try:
        # Verify entity exists
        _ = db.entity.get_or_raise(entity_id)
        
        # Get intelligence data using service
        intel_data = db.intelligence.get_intelligence_data(entity_id)
        return intel_data.active_jobs + intel_data.job_history
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Entity not found")


@router.get(
    "/known-persons",
    tags=["face-recognition"],
    summary="Get All Known Persons",
    description="Get all known persons (identified by face recognition).",
    operation_id="get_all_known_persons",
)
async def get_all_known_persons(
    user: UserPayload | None = Depends(require_permission("media_store_read")),
    db: DBService = Depends(get_db_service),
) -> list[intel_schemas.KnownPersonSchema]:
    """Get all known persons."""
    _ = user
    return db.known_person.get_all()


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
    db: DBService = Depends(get_db_service),
) -> intel_schemas.KnownPersonSchema:
    """Get known person details."""
    _ = user

    person = db.known_person.get(person_id)
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
    db: DBService = Depends(get_db_service),
) -> list[intel_schemas.FaceSchema]:
    """Get all faces for a known person."""
    _ = user

    if not db.known_person.exists(person_id):
        raise HTTPException(status_code=404, detail="Known person not found")

    return db.face.get_by_known_person_id(person_id)


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
    db: DBService = Depends(get_db_service),
) -> intel_schemas.KnownPersonSchema:
    """Update person name."""
    _ = user

    result = db.known_person.update_name(person_id, body.name)
    if not result:
        raise HTTPException(status_code=404, detail="Known person not found")

    return result


