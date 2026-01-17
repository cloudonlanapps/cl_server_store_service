from __future__ import annotations

import asyncio

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    Query,
    Request,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import config_service as cfg_service
from . import models, schemas
from .auth import UserPayload, require_admin, require_permission
from .database import SessionLocal, get_db
from .service import EntityService

router = APIRouter()


async def _trigger_async_jobs_background(entity_id: int) -> None:
    """Trigger async jobs in background with independent DB session.

    Creates a fresh database session for background processing to avoid
    holding the request's session while async jobs are submitted.

    Args:
        entity_id: Entity ID to process
    """
    db = SessionLocal()
    try:
        service = EntityService(db)
        entity = db.query(models.Entity).filter(models.Entity.id == entity_id).first()
        if entity:
            _ = await service.trigger_async_jobs(entity)  # TODO: Do we really need to await here?
    finally:
        db.close()


@router.get(
    "/entities",
    tags=["entity"],
    summary="Get Entities",
    description="Retrieves a paginated list of media entities, optionally at a specific version.",
    operation_id="get_entities",
    responses={200: {"model": schemas.PaginatedResponse, "description": "Successful Response"}},
)
async def get_entities(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    version: int | None = Query(
        None, description="Optional version number to retrieve for all entities"
    ),
    filter_param: str | None = Query(
        None, title="Filter Param", description="Optional filter string"
    ),
    search_query: str | None = Query(
        None, title="Search Query", description="Optional search query"
    ),
    exclude_deleted: bool = Query(
        False, title="Exclude Deleted", description="Whether to exclude soft-deleted entities"
    ),
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
) -> schemas.PaginatedResponse:
    """
    Get all entities with pagination.
    """
    _ = user
    service = EntityService(db)
    items, total_count = service.get_entities(
        page=page,
        page_size=page_size,
        version=version,
        filter_param=filter_param,
        search_query=search_query,
        exclude_deleted=exclude_deleted,
    )

    # Calculate pagination metadata
    import math

    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0
    has_next = page < total_pages
    has_prev = page > 1

    pagination = schemas.PaginationMetadata(
        page=page,
        page_size=page_size,
        total_items=total_count,
        total_pages=total_pages,
        has_next=has_next,
        has_prev=has_prev,
    )

    return schemas.PaginatedResponse(items=items, pagination=pagination)


@router.post(
    "/entities",
    tags=["entity"],
    summary="Create Entity",
    description="Creates a new entity.",
    operation_id="create_entity",
    status_code=status.HTTP_201_CREATED,
    responses={201: {"model": schemas.Item, "description": "Successful Response"}},
)
async def create_entity(
    is_collection: bool = Form(..., title="Is Collection"),
    label: str | None = Form(None, title="Label"),
    description: str | None = Form(None, title="Description"),
    parent_id: int | None = Form(None, title="Parent Id"),
    image: UploadFile | None = File(None, title="Image"),
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_write")),
) -> schemas.Item:
    service = EntityService(db)

    # Extract user_id from JWT payload (None in demo mode)
    user_id = user.id if user else None

    # Create body object from form fields
    body = schemas.BodyCreateEntity(
        is_collection=is_collection,
        label=label,
        description=description,
        parent_id=parent_id,
    )

    # Read file bytes and filename if provided
    file_bytes = None
    filename = "file"
    if image:
        file_bytes = await image.read()
        filename = image.filename or "file"

    try:
        item = service.create_entity(body, file_bytes, filename, user_id)

        # Trigger async jobs for images (NON-BLOCKING)
        # Uses independent DB session to avoid holding request session
        if not is_collection and file_bytes and item.id:
            _ = asyncio.create_task(_trigger_async_jobs_background(item.id))

        return item
    except ValueError as e:
        # Validation errors or invalid file format
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))
    except RuntimeError as e:
        # Tool execution failure (ExifTool, ffprobe)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except Exception as e:
        # General extraction failure
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))


@router.delete(
    "/entities",
    tags=["entity"],
    summary="Delete Collection",
    description="Deletes the entire collection.",
    operation_id="delete_collection",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={204: {"description": "All entities deleted successfully"}},
)
async def delete_collection(
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_write")),
):
    _ = user
    service = EntityService(db)
    service.delete_all_entities()
    # No return statement - FastAPI will return 204 automatically


@router.get(
    "/entities/{entity_id}",
    tags=["entity"],
    summary="Get Entity",
    description="Retrieves a specific media entity by its ID, optionally at a specific version.",
    operation_id="get_entity",
    responses={200: {"model": schemas.Item, "description": "Successful Response"}},
)
async def get_entity(
    entity_id: int = Path(..., title="Entity Id"),
    version: int | None = Query(
        None, title="Version", description="Optional version number to retrieve"
    ),
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
) -> schemas.Item:
    _ = user
    service = EntityService(db)
    item = service.get_entity_by_id(entity_id, version=version)
    if not item:
        if version is not None:
            raise HTTPException(
                status_code=404,
                detail=f"Entity {entity_id} version {version} not found",
            )
        raise HTTPException(status_code=404, detail="Entity not found")
    return item


@router.put(
    "/entities/{entity_id}",
    tags=["entity"],
    summary="Put Entity",
    description="Update an existing entity.",
    operation_id="put_entity",
    responses={200: {"model": schemas.Item, "description": "Successful Response"}},
)
async def put_entity(
    entity_id: int = Path(..., title="Entity Id"),
    is_collection: bool = Form(..., title="Is Collection"),
    label: str = Form(..., title="Label"),
    description: str | None = Form(None, title="Description"),
    parent_id: int | None = Form(None, title="Parent Id"),
    image: UploadFile | None = File(None, title="Image"),
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_write")),
) -> schemas.Item:
    service = EntityService(db)

    # Extract user_id from JWT payload (None in demo mode)
    user_id = user.id if user else None

    # Create body object from form fields
    body = schemas.BodyUpdateEntity(
        is_collection=is_collection,
        label=label,
        description=description,
        parent_id=parent_id,
    )

    # Read file bytes and filename if provided
    file_bytes: bytes | None = None
    filename = "file"
    if image:
        file_bytes = await image.read()
        filename = image.filename or "file"

    try:
        # Update entity (file is optional - None updates only metadata)
        item = service.update_entity(entity_id, body, file_bytes, filename, user_id)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")

        # Trigger async jobs if new file uploaded (NON-BLOCKING)
        # Uses independent DB session to avoid holding request session
        if file_bytes and not is_collection:
            _ = asyncio.create_task(_trigger_async_jobs_background(entity_id))

        return item
    except ValueError as e:
        # Validation errors or invalid file format
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))
    except RuntimeError as e:
        # Tool execution failure (ExifTool, ffprobe)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except HTTPException:
        # Re-raise HTTPException (like 404) without wrapping
        raise
    except Exception as e:
        # General extraction failure
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))


@router.patch(
    "/entities/{entity_id}",
    tags=["entity"],
    summary="Patch Entity",
    description="Partially updates an entity. Use this endpoint to soft delete (is_deleted=true) or restore (is_deleted=false) an entity.",
    operation_id="patch_entity",
    responses={
        200: {"model": schemas.Item, "description": "Successful Response"},
        404: {"description": "Entity not found"},
    },
)
async def patch_entity(
    request: Request,
    entity_id: int,
    label: str | None = Form(None, title="Label"),
    description: str | None = Form(None, title="Description"),
    parent_id: str = Form("__UNSET__", title="Parent Id"),
    is_deleted: str = Form("__UNSET__", title="Is Deleted"),
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_write")),
) -> schemas.Item:
    service = EntityService(db)

    # Extract user_id from JWT payload (None in demo mode)
    user_id = user.id if user else None

    # Get raw form data to check if fields with empty values were actually sent
    form_data = await request.form()
    form_keys = set(form_data.keys())

    # Create body object from form fields
    # Handle type conversions for form data (strings to proper types)
    patch_data = {}
    if label is not None:
        patch_data["label"] = label
    if description is not None:
        patch_data["description"] = description
    # Check if parent_id was actually sent (even as empty string)
    if "parent_id" in form_keys:
        # Empty string means set to None, otherwise parse as int
        parent_id_value = form_data.get("parent_id", "")
        patch_data["parent_id"] = None if parent_id_value == "" else int(parent_id_value)
    # Check if is_deleted was actually sent
    if "is_deleted" in form_keys:
        # Convert string boolean to actual boolean
        is_deleted_value = form_data.get("is_deleted", "false")
        patch_data["is_deleted"] = is_deleted_value.lower() in ("true", "1", "yes")

    # Use model_construct to preserve explicit None values as "set"
    body = schemas.BodyPatchEntity.model_construct(**patch_data, _fields_set=set(patch_data.keys()))

    item = service.patch_entity(entity_id, body, user_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    return item


@router.delete(
    "/entities/{entity_id}",
    tags=["entity"],
    summary="Delete Entity",
    description="Permanently deletes an entity and its associated file (Hard Delete).",
    operation_id="delete_entity",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Entity deleted successfully"},
        404: {"description": "Entity not found"},
    },
)
async def delete_entity(
    entity_id: int,
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_write")),
):
    _ = user
    service = EntityService(db)
    item = service.delete_entity(entity_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    # No return statement - FastAPI will return 204 automatically


@router.get(
    "/entities/{entity_id}/versions",
    tags=["entity"],
    summary="Get Entity Versions",
    description="Retrieves all versions of a specific entity.",
    operation_id="get_entity_versions",
    responses={200: {"description": "Successful Response"}},
)
async def get_entity_versions(
    entity_id: int = Path(..., title="Entity Id"),
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
) -> list[dict[str, int | None]]:
    _ = user
    service = EntityService(db)
    versions = service.get_entity_versions(entity_id)
    if not versions:
        raise HTTPException(status_code=404, detail="Entity not found or no versions available")
    return versions


# Admin configuration endpoints
@router.get(
    "/admin/config",
    tags=["admin"],
    summary="Get Configuration",
    description="Get current service configuration. Requires admin access.",
    operation_id="get_config_admin_config_get",
    responses={200: {"model": schemas.ConfigResponse, "description": "Successful Response"}},
)
async def get_config(
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_admin),
) -> schemas.ConfigResponse:
    """Get current service configuration.

    Requires admin access.
    """
    _ = user
    config_service = cfg_service.ConfigService(db)

    # Get config metadata
    metadata = config_service.get_config_metadata("read_auth_enabled")

    if metadata:
        value_str = str(metadata["value"]) if metadata["value"] is not None else "false"
        updated_at = metadata["updated_at"]
        updated_by = metadata["updated_by"]
        # Invert logic: read_auth_enabled=false means guest_mode=true
        read_auth_enabled = value_str.lower() == "true"
        return schemas.ConfigResponse(
            guest_mode=not read_auth_enabled,
            updated_at=int(updated_at)
            if updated_at is not None and not isinstance(updated_at, str)
            else None,
            updated_by=str(updated_by)
            if updated_by is not None and not isinstance(updated_by, int)
            else None,
        )

    # Default if not found: read_auth_enabled=false means guest_mode=true
    return schemas.ConfigResponse(guest_mode=True, updated_at=None, updated_by=None)


@router.put(
    "/admin/config/guest-mode",
    tags=["admin"],
    summary="Update Guest Mode Configuration",
    description="Toggle guest mode (authentication requirement). Requires admin access.",
    operation_id="update_guest_mode_admin_config_guest_mode_put",
    responses={200: {"description": "Successful Response"}},
)
async def update_guest_mode(
    guest_mode: bool = Form(..., title="Guest Mode"),
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_admin),
) -> dict[str, bool | str]:
    """Update guest mode configuration.

    Requires admin access. Changes are persistent and take effect immediately.
    guest_mode=true means no authentication required.
    guest_mode=false means authentication required.
    """

    from .config_service import ConfigService

    config_service = ConfigService(db)

    # Get user ID from JWT
    user_id = user.id if user else None

    # Invert logic: guest_mode=true means read_auth_enabled=false
    config_service.set_read_auth_enabled(not guest_mode, user_id)

    return {
        "guest_mode": guest_mode,
        "message": "Configuration updated successfully",
    }


class RootResponse(BaseModel):
    status: str
    service: str
    version: str
    guestMode: str


@router.get(
    "/",
    summary="Health Check",
    description="Returns service health status",
    response_model=RootResponse,
    operation_id="root_get",
)
async def root(db: Session = Depends(get_db)):
    from .config_service import ConfigService

    config_service = ConfigService(db)
    read_auth_enabled = config_service.get_read_auth_enabled()
    # guestMode is "on" when read_auth is disabled (public read access)
    guest_mode = "off" if read_auth_enabled else "on"

    return RootResponse(
        status="healthy", service="CoLAN Store Server", version="v1", guestMode=guest_mode
    )


# Face detection and similarity search endpoints
@router.get(
    "/entities/{entity_id}/faces",
    tags=["entity", "face-detection"],
    summary="Get Entity Faces",
    description="Retrieves all detected faces for a specific entity.",
    operation_id="get_entity_faces",
    responses={
        200: {"model": list[schemas.FaceResponse], "description": "List of detected faces"},
        404: {"description": "Entity not found"},
    },
)
async def get_entity_faces(
    entity_id: int = Path(..., title="Entity Id"),
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
) -> list[schemas.FaceResponse]:
    """Get all faces detected in an entity."""
    _ = user
    service = EntityService(db)

    # Check if entity exists
    entity = service.get_entity_by_id(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    return service.get_entity_faces(entity_id)


@router.get(
    "/faces/{face_id}/embedding",
    tags=["face-detection"],
    summary="Download Face Embedding",
    description="Downloads the face embedding vector from Qdrant as a .npy file.",
    operation_id="download_face_embedding",
    responses={
        200: {"description": "Face embedding as .npy file"},
        404: {"description": "Face or embedding not found"},
    },
)
async def download_face_embedding(
    face_id: int = Path(..., title="Face Id"),
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
):
    """Download face embedding from Qdrant vector store."""
    _ = user
    import io

    import numpy as np
    from fastapi.responses import Response

    from .compute_singleton import get_pysdk_config
    from .face_store_singleton import get_face_store
    from .models import Face

    # Check if face exists in database
    face = db.query(Face).filter(Face.id == face_id).first()
    if not face:
        raise HTTPException(status_code=404, detail="Face not found")

    # Get face store and retrieve embedding
    pysdk_config = get_pysdk_config()
    face_store = get_face_store(pysdk_config)

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
    responses={
        200: {"description": "CLIP embedding as .npy file"},
        404: {"description": "Entity or embedding not found"},
    },
)
async def download_entity_embedding(
    entity_id: int = Path(..., title="Entity Id"),
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
):
    """Download entity CLIP embedding from Qdrant vector store."""
    _ = user
    import io

    import numpy as np
    from fastapi.responses import Response

    from .models import Entity

    # Check if entity exists in database
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Get Qdrant store and retrieve embedding
    from .qdrant_singleton import get_qdrant_store

    qdrant_store = get_qdrant_store()

    # Retrieve from Qdrant using entity_id as point_id
    point = qdrant_store.get_vector(id=entity_id)

    if not point:
        raise HTTPException(status_code=404, detail="Entity embedding not found in vector store")

    # Extract vector from Qdrant point

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
    responses={
        200: {"model": list[schemas.EntityJobResponse], "description": "List of entity jobs"},
        404: {"description": "Entity not found"},
    },
)
async def get_entity_jobs(
    entity_id: int = Path(..., title="Entity Id"),
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
) -> list[schemas.EntityJobResponse]:
    """Get all jobs for an entity."""
    _ = user
    service = EntityService(db)

    # Check if entity exists
    entity = service.get_entity_by_id(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    return service.get_entity_jobs(entity_id)


@router.get(
    "/entities/{entity_id}/similar",
    tags=["entity", "search"],
    summary="Find Similar Images",
    description="Find similar images using CLIP embeddings. Requires the entity to have a CLIP embedding.",
    operation_id="find_similar_images",
    responses={
        200: {"model": schemas.SimilarImagesResponse, "description": "List of similar images"},
        404: {"description": "Entity not found or no embedding available"},
    },
)
async def find_similar_images(
    entity_id: int = Path(..., title="Entity Id"),
    limit: int = Query(5, ge=1, le=50, description="Maximum number of results"),
    score_threshold: float = Query(0.85, ge=0.0, le=1.0, description="Minimum similarity score"),
    include_details: bool = Query(False, description="Include entity details in results"),
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
) -> schemas.SimilarImagesResponse:
    """Find similar images using CLIP embeddings."""
    _ = user
    service = EntityService(db)

    # Check if entity exists
    entity = service.get_entity_by_id(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Search for similar images
    results = service.search_similar_images(entity_id, limit, score_threshold)

    if not results:
        # Could be no embedding or no similar images found
        raise HTTPException(
            status_code=404,
            detail="No similar images found. Entity may not have an embedding yet.",
        )

    # Optionally include entity details
    if include_details:
        for result in results:
            result.entity = service.get_entity_by_id(result.entity_id)

    return schemas.SimilarImagesResponse(
        results=results,
        query_entity_id=entity_id,
    )


# Face recognition and known persons endpoints
@router.get(
    "/faces/{face_id}/similar",
    tags=["face-recognition"],
    summary="Find Similar Faces",
    description="Find similar faces using face embeddings. Requires the face to have an embedding.",
    operation_id="find_similar_faces",
    responses={
        200: {"model": schemas.SimilarFacesResponse, "description": "List of similar faces"},
        404: {"description": "Face not found or no embedding available"},
    },
)
async def find_similar_faces(
    face_id: int = Path(..., title="Face Id"),
    limit: int = Query(5, ge=1, le=50, description="Maximum number of results"),
    threshold: float = Query(0.7, ge=0.0, le=1.0, description="Minimum similarity score"),
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
) -> schemas.SimilarFacesResponse:
    """Find similar faces using face embeddings."""
    _ = user
    service = EntityService(db)

    # Check if face exists
    from .models import Face

    face = db.query(Face).filter(Face.id == face_id).first()
    if not face:
        raise HTTPException(status_code=404, detail="Face not found")

    # Search for similar faces
    results = service.search_similar_faces_by_id(face_id, limit, threshold)

    if not results:
        # Could be no embedding or no similar faces found
        raise HTTPException(
            status_code=404,
            detail="No similar faces found. Face may not have an embedding yet.",
        )

    return schemas.SimilarFacesResponse(
        results=results,
        query_face_id=face_id,
    )


@router.get(
    "/faces/{face_id}/matches",
    tags=["face-recognition"],
    summary="Get Face Matches",
    description="Get all match records for a face (similarity history).",
    operation_id="get_face_matches",
    responses={
        200: {"model": list[schemas.FaceMatchResult], "description": "List of face matches"},
        404: {"description": "Face not found"},
    },
)
async def get_face_matches(
    face_id: int = Path(..., title="Face Id"),
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
) -> list[schemas.FaceMatchResult]:
    """Get all match records for a face."""
    _ = user
    service = EntityService(db)

    # Check if face exists
    from .models import Face

    face = db.query(Face).filter(Face.id == face_id).first()
    if not face:
        raise HTTPException(status_code=404, detail="Face not found")

    return service.get_face_matches(face_id)


@router.get(
    "/known-persons",
    tags=["face-recognition"],
    summary="Get All Known Persons",
    description="Get all known persons (identified by face recognition).",
    operation_id="get_all_known_persons",
    responses={
        200: {"model": list[schemas.KnownPersonResponse], "description": "List of known persons"},
    },
)
async def get_all_known_persons(
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
) -> list[schemas.KnownPersonResponse]:
    """Get all known persons."""
    _ = user
    service = EntityService(db)
    return service.get_all_known_persons()


@router.get(
    "/known-persons/{person_id}",
    tags=["face-recognition"],
    summary="Get Known Person",
    description="Get details of a specific known person.",
    operation_id="get_known_person",
    responses={
        200: {"model": schemas.KnownPersonResponse, "description": "Known person details"},
        404: {"description": "Known person not found"},
    },
)
async def get_known_person(
    person_id: int = Path(..., title="Person Id"),
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
) -> schemas.KnownPersonResponse:
    """Get known person details."""
    _ = user
    service = EntityService(db)

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
    responses={
        200: {"model": list[schemas.FaceResponse], "description": "List of faces"},
        404: {"description": "Known person not found"},
    },
)
async def get_person_faces(
    person_id: int = Path(..., title="Person Id"),
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
) -> list[schemas.FaceResponse]:
    """Get all faces for a known person."""
    _ = user
    service = EntityService(db)

    # Check if person exists
    from .models import KnownPerson

    person = db.query(KnownPerson).filter(KnownPerson.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Known person not found")

    return service.get_known_person_faces(person_id)


@router.patch(
    "/known-persons/{person_id}",
    tags=["face-recognition"],
    summary="Update Person Name",
    description="Update the name of a known person.",
    operation_id="update_person_name",
    responses={
        200: {"model": schemas.KnownPersonResponse, "description": "Updated known person"},
        404: {"description": "Known person not found"},
    },
)
async def update_person_name(
    person_id: int = Path(..., title="Person Id"),
    body: schemas.UpdatePersonNameRequest = Body(...),
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("media_store_write")),
) -> schemas.KnownPersonResponse:
    """Update person name."""
    _ = user
    service = EntityService(db)

    result = service.update_known_person_name(person_id, body.name)
    if not result:
        raise HTTPException(status_code=404, detail="Known person not found")

    return result
