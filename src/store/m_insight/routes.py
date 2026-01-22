from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request
from sqlalchemy.orm import Session

from store.common import models, schemas
from store.common.auth import UserPayload, require_permission
from store.common.database import get_db
from store.store.config import StoreConfig

from . import models as intel_models
from . import schemas as intel_schemas
from .retrieval_service import IntelligenceRetrieveService

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
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
    request: Request = None,  # pyright: ignore[reportGeneralTypeIssues]
) -> list[intel_schemas.FaceResponse]:
    """Get all faces detected in an entity."""
    _ = user
    config: StoreConfig = request.app.state.config
    service = IntelligenceRetrieveService(db, config)

    # Check if entity exists
    entity = db.query(models.Entity).filter(models.Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    return service.get_entity_faces(entity_id)


@router.get(
    "/faces/{face_id}/embedding",
    tags=["face-detection"],
    summary="Download Face Embedding",
    description="Downloads the face embedding vector from Qdrant as a .npy file.",
    operation_id="download_face_embedding",
)
async def download_face_embedding(
    face_id: int = Path(..., title="Face Id"),
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
    request: Request = None,  # pyright: ignore[reportGeneralTypeIssues]
):
    """Download face embedding from Qdrant vector store."""
    _ = user
    import io

    import numpy as np
    from fastapi.responses import Response

    from .models import Face

    # Get face store and retrieve embedding
    config: StoreConfig = request.app.state.config
    from .vector_stores import get_face_store

    # Get face store and retrieve embedding
    face_store = get_face_store(
        url=config.qdrant_url,
        collection_name=config.qdrant_collections.face_embedding_collection_name,
        vector_size=getattr(config, "face_vector_size", 512),
    )

    # Retrieve from Qdrant using face_id as point_id
    point = face_store.get_vector(id=face_id)

    if not point:
        raise HTTPException(status_code=404, detail="Face embedding not found in vector store")

    # Serialize to .npy format in memory
    buffer = io.BytesIO()
    np.save(buffer, point.embedding)
    _ = buffer.seek(0)

    return Response(
        content=buffer.getvalue(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename=face_{face_id}_embedding.npy"},
    )


@router.get(
    "/entities/{entity_id}/embedding",
    tags=["entity", "clip-embedding"],
    summary="Download Entity CLIP Embedding",
    description="Downloads the CLIP image embedding vector from Qdrant as a .npy file.",
    operation_id="download_entity_embedding",
)
async def download_entity_embedding(
    entity_id: int = Path(..., title="Entity Id"),
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
    request: Request = None,  # pyright: ignore[reportGeneralTypeIssues]
):
    """Download entity CLIP embedding from Qdrant vector store."""
    _ = user
    import io

    import numpy as np
    from fastapi.responses import Response

    from store.common.models import Entity

    # Check if entity exists in database
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Get Qdrant store and retrieve embedding
    config: StoreConfig = request.app.state.config
    from .vector_stores import get_clip_store

    qdrant_store = get_clip_store(
        url=config.qdrant_url,
        collection_name=config.qdrant_collections.clip_embedding_collection_name,
    )

    # Retrieve from Qdrant using entity_id as point_id
    point = qdrant_store.get_vector(id=entity_id)

    if not point:
        raise HTTPException(status_code=404, detail="Entity embedding not found in vector store")

    # Serialize to .npy format in memory
    buffer = io.BytesIO()
    np.save(buffer, point.embedding)
    _ = buffer.seek(0)

    return Response(
        content=buffer.getvalue(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename=entity_{entity_id}_clip_embedding.npy"
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
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
    request: Request = None,  # pyright: ignore[reportGeneralTypeIssues]
) -> list[intel_schemas.EntityJobResponse]:
    """Get all jobs for an entity."""
    _ = user
    config: StoreConfig = request.app.state.config
    service = IntelligenceRetrieveService(db, config)

    # Check if entity exists
    entity = db.query(models.Entity).filter(models.Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    return service.get_entity_jobs(entity_id)


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
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
    request: Request = None,  # pyright: ignore[reportGeneralTypeIssues]
) -> intel_schemas.SimilarImagesResponse:
    """Find similar images using CLIP embeddings."""
    _ = user
    config: StoreConfig = request.app.state.config
    service = IntelligenceRetrieveService(db, config)

    # Check if entity exists
    entity = db.query(models.Entity).filter(models.Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Search for similar images
    results = service.search_similar_images(entity_id, limit, score_threshold)

    if not results:
        raise HTTPException(
            status_code=404,
            detail="No similar images found. Entity may not have an embedding yet.",
        )

    # Optionally include entity details
    if include_details:
        from store.store.service import EntityService

        entity_service = EntityService(db, config)
        for result in results:
            result.entity = entity_service.get_entity_by_id(result.image_id)

    return intel_schemas.SimilarImagesResponse(
        results=results,
        query_image_id=entity_id,
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
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
    request: Request = None,  # pyright: ignore[reportGeneralTypeIssues]
) -> intel_schemas.SimilarFacesResponse:
    """Find similar faces using face embeddings."""
    _ = user
    config: StoreConfig = request.app.state.config
    service = IntelligenceRetrieveService(db, config)

    # Check if face exists
    face = db.query(intel_models.Face).filter(intel_models.Face.id == face_id).first()
    if not face:
        raise HTTPException(status_code=404, detail="Face not found")

    # Search for similar faces
    results = service.search_similar_faces_by_id(face_id, limit, threshold)

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
    "/faces/{face_id}/matches",
    tags=["face-recognition"],
    summary="Get Face Matches",
    description="Get all match records for a face (similarity history).",
    operation_id="get_face_matches",
)
async def get_face_matches(
    face_id: int = Path(..., title="Face Id"),
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
    request: Request = None,  # pyright: ignore[reportGeneralTypeIssues]
) -> list[intel_schemas.FaceMatchResult]:
    """Get all match records for a face."""
    _ = user
    config: StoreConfig = request.app.state.config
    service = IntelligenceRetrieveService(db, config)

    # Check if face exists
    face = db.query(intel_models.Face).filter(intel_models.Face.id == face_id).first()
    if not face:
        raise HTTPException(status_code=404, detail="Face not found")

    return service.get_face_matches(face_id)


@router.get(
    "/known-persons",
    tags=["face-recognition"],
    summary="Get All Known Persons",
    description="Get all known persons (identified by face recognition).",
    operation_id="get_all_known_persons",
)
async def get_all_known_persons(
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
    request: Request = None,  # pyright: ignore[reportGeneralTypeIssues]
) -> list[intel_schemas.KnownPersonResponse]:
    """Get all known persons."""
    _ = user
    config: StoreConfig = request.app.state.config
    service = IntelligenceRetrieveService(db, config)
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
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
    request: Request = None,  # pyright: ignore[reportGeneralTypeIssues]
) -> intel_schemas.KnownPersonResponse:
    """Get known person details."""
    _ = user
    config: StoreConfig = request.app.state.config
    service = IntelligenceRetrieveService(db, config)

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
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
    request: Request = None,  # pyright: ignore[reportGeneralTypeIssues]
) -> list[intel_schemas.FaceResponse]:
    """Get all faces for a known person."""
    _ = user
    config: StoreConfig = request.app.state.config
    service = IntelligenceRetrieveService(db, config)

    # Check if person exists
    person = (
        db.query(intel_models.KnownPerson)
        .filter(intel_models.KnownPerson.id == person_id)
        .first()
    )
    if not person:
        raise HTTPException(status_code=404, detail="Known person not found")

    return service.get_known_person_faces(person_id)


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
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_write")),
    request: Request = None,  # pyright: ignore[reportGeneralTypeIssues]
) -> intel_schemas.KnownPersonResponse:
    """Update person name."""
    _ = user
    config: StoreConfig = request.app.state.config
    service = IntelligenceRetrieveService(db, config)

    result = service.update_known_person_name(person_id, body.name)
    if not result:
        raise HTTPException(status_code=404, detail="Known person not found")

    return result
