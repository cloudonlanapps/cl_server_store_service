from __future__ import annotations

from typing import List, Optional

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import auth, database, schemas, service
from .database import get_db
from .service import EntityService

router = APIRouter()


@router.get(
    "/entity/",
    tags=["entity"],
    summary="Get Entities",
    description="Retrieves a paginated list of media entities, optionally at a specific version.",
    operation_id="get_entities_entity__get",
    responses={
        200: {"model": schemas.PaginatedResponse, "description": "Successful Response"}
    },
)
async def get_entities(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    version: Optional[int] = Query(
        None, description="Optional version number to retrieve for all entities"
    ),
    filter_param: Optional[str] = Query(
        None, title="Filter Param", description="Optional filter string"
    ),
    search_query: Optional[str] = Query(
        None, title="Search Query", description="Optional search query"
    ),
    db: Session = Depends(get_db),
    current_user: Optional[dict] = Depends(auth.get_current_user_with_read_permission),
) -> schemas.PaginatedResponse:
    service = EntityService(db)
    items, total_count = service.get_entities(
        page=page,
        page_size=page_size,
        version=version,
        filter_param=filter_param,
        search_query=search_query,
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
    "/entity/",
    tags=["entity"],
    summary="Create Entity",
    description="Creates a new entity.",
    operation_id="create_entity_entity__post",
    status_code=status.HTTP_201_CREATED,
    responses={201: {"model": schemas.Item, "description": "Successful Response"}},
)
async def create_entity(
    is_collection: bool = Form(..., title="Is Collection"),
    label: Optional[str] = Form(None, title="Label"),
    description: Optional[str] = Form(None, title="Description"),
    parent_id: Optional[int] = Form(None, title="Parent Id"),
    image: Optional[UploadFile] = File(None, title="Image"),
    db: Session = Depends(get_db),
    current_user: Optional[dict] = Depends(auth.get_current_user_with_write_permission),
) -> schemas.Item:
    service = EntityService(db)

    # Extract user_id from JWT payload (None in demo mode)
    user_id = current_user.get("sub") if current_user else None

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
        return service.create_entity(body, file_bytes, filename, user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.delete(
    "/entity/",
    tags=["entity"],
    summary="Delete Collection",
    description="Deletes the entire collection.",
    operation_id="delete_collection_entity__delete",
    responses={200: {"model": None, "description": "Successful Response"}},
)
async def delete_collection(
    db: Session = Depends(get_db),
    current_user: dict = Depends(auth.get_current_user_with_write_permission),
) -> JSONResponse:
    service = EntityService(db)
    service.delete_all_entities()
    return JSONResponse(content=None, status_code=status.HTTP_200_OK)


@router.get(
    "/entity/{entity_id}",
    tags=["entity"],
    summary="Get Entity",
    description="Retrieves a specific media entity by its ID, optionally at a specific version.",
    operation_id="get_entity_entity__entity_id__get",
    responses={200: {"model": schemas.Item, "description": "Successful Response"}},
)
async def get_entity(
    entity_id: int = Path(..., title="Entity Id"),
    version: Optional[int] = Query(
        None, title="Version", description="Optional version number to retrieve"
    ),
    content: Optional[str] = Query(
        None, title="Content", description="Optional content query"
    ),
    db: Session = Depends(get_db),
    current_user: Optional[dict] = Depends(auth.get_current_user_with_read_permission),
) -> schemas.Item:
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
    "/entity/{entity_id}",
    tags=["entity"],
    summary="Put Entity",
    description="Update an existing entity.",
    operation_id="put_entity_entity__entity_id__put",
    responses={200: {"model": schemas.Item, "description": "Successful Response"}},
)
async def put_entity(
    entity_id: int = Path(..., title="Entity Id"),
    is_collection: bool = Form(..., title="Is Collection"),
    label: str = Form(..., title="Label"),
    description: Optional[str] = Form(None, title="Description"),
    parent_id: Optional[int] = Form(None, title="Parent Id"),
    image: Optional[UploadFile] = File(None, title="Image"),
    db: Session = Depends(get_db),
    current_user: Optional[dict] = Depends(auth.get_current_user_with_write_permission),
) -> schemas.Item:
    service = EntityService(db)

    # Extract user_id from JWT payload (None in demo mode)
    user_id = current_user.get("sub") if current_user else None

    # Create body object from form fields
    body = schemas.BodyUpdateEntity(
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
        item = service.update_entity(entity_id, body, file_bytes, filename, user_id)
        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found"
            )
        return item
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.patch(
    "/entity/{entity_id}",
    tags=["entity"],
    summary="Patch Entity",
    description="Partially updates an entity. Use this endpoint to soft delete (is_deleted=true) or restore (is_deleted=false) an entity.",
    operation_id="patch_entity_entity__entity_id__patch",
    responses={
        200: {"model": schemas.Item, "description": "Successful Response"},
        404: {"description": "Entity not found"},
    },
)
async def patch_entity(
    entity_id: int,
    body: schemas.BodyPatchEntity = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: Optional[dict] = Depends(auth.get_current_user_with_write_permission),
) -> schemas.Item:
    service = EntityService(db)

    # Extract user_id from JWT payload (None in demo mode)
    user_id = current_user.get("sub") if current_user else None

    item = service.patch_entity(entity_id, body, user_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found"
        )
    return item


@router.delete(
    "/entity/{entity_id}",
    tags=["entity"],
    summary="Delete Entity",
    description="Permanently deletes an entity and its associated file (Hard Delete).",
    operation_id="delete_entity_entity__entity_id__delete",
    responses={
        200: {"model": schemas.Item, "description": "Successful Response"},
        404: {"description": "Entity not found"},
    },
)
async def delete_entity(
    entity_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(auth.get_current_user_with_write_permission),
) -> schemas.Item:
    service = EntityService(db)
    item = service.delete_entity(entity_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found"
        )
    return item


@router.get(
    "/entity/{entity_id}/versions",
    tags=["entity"],
    summary="Get Entity Versions",
    description="Retrieves all versions of a specific entity.",
    operation_id="get_entity_versions_entity__entity_id__versions_get",
    responses={200: {"model": List[dict], "description": "Successful Response"}},
)
async def get_entity_versions(
    entity_id: int = Path(..., title="Entity Id"),
    db: Session = Depends(get_db),
    current_user: Optional[dict] = Depends(auth.get_current_user_with_read_permission),
) -> List[dict]:
    service = EntityService(db)
    versions = service.get_entity_versions(entity_id)
    if not versions:
        raise HTTPException(
            status_code=404, detail="Entity not found or no versions available"
        )
    return versions


# Admin configuration endpoints
@router.get(
    "/admin/config",
    tags=["admin"],
    summary="Get Configuration",
    description="Get current service configuration. Requires admin access.",
    operation_id="get_config_admin_config_get",
    responses={
        200: {"model": schemas.ConfigResponse, "description": "Successful Response"}
    },
)
async def get_config(
    db: Session = Depends(get_db),
    current_user: Optional[dict] = Depends(auth.get_current_user_with_write_permission),
) -> schemas.ConfigResponse:
    """Get current service configuration.

    Requires admin access.
    """
    # Check if user is admin
    if not current_user or not current_user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )

    from .config_service import ConfigService

    config_service = ConfigService(db)

    # Get config metadata
    metadata = config_service.get_config_metadata("read_auth_enabled")

    if metadata:
        return schemas.ConfigResponse(
            read_auth_enabled=metadata["value"].lower() == "true",
            updated_at=metadata["updated_at"],
            updated_by=metadata["updated_by"],
        )

    # Default if not found
    return schemas.ConfigResponse(
        read_auth_enabled=False, updated_at=None, updated_by=None
    )


@router.put(
    "/admin/config/read-auth",
    tags=["admin"],
    summary="Update Read Auth Configuration",
    description="Toggle read authentication requirement. Requires admin access.",
    operation_id="update_read_auth_config_admin_config_read_auth_put",
    responses={200: {"model": dict, "description": "Successful Response"}},
)
async def update_read_auth_config(
    config: schemas.UpdateReadAuthConfig,
    db: Session = Depends(get_db),
    current_user: Optional[dict] = Depends(auth.get_current_user_with_write_permission),
) -> dict:
    """Update read authentication configuration.

    Requires admin access. Changes are persistent and take effect immediately.
    """
    # Check if user is admin
    if not current_user or not current_user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )

    from .config_service import ConfigService

    config_service = ConfigService(db)

    # Get user ID from JWT
    user_id = current_user.get("sub") if current_user else None

    # Update configuration
    config_service.set_read_auth_enabled(config.enabled, user_id)

    return {
        "read_auth_enabled": config.enabled,
        "message": "Configuration updated successfully",
    }


@router.post(
    "/entity/{entity_id}/face-detection-results",
    tags=["inference"],
    summary="Accept Face Detection Results",
    description="Stub endpoint to accept face detection results from inference service. Data is accepted but not stored.",
    status_code=status.HTTP_200_OK,
)
async def accept_face_detection_results(
    entity_id: int = Path(..., title="Entity ID"),
    results: dict = Body(..., title="Face Detection Results"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Stub endpoint to accept face detection results from the inference service.

    This is a placeholder implementation that accepts the face detection data
    but does not store it. In future, this can be enhanced to store face
    detection results in the media store.

    Args:
        entity_id: The ID of the media entity
        results: Face detection results including faces, face_count, etc.

    Returns:
        Confirmation message
    """
    # Stub: accept and ignore the data
    # In future, store results in media_store
    return {
        "status": "accepted",
        "entity_id": entity_id,
        "message": "Face detection results received and stored",
    }


# Job Management Endpoints (from compute service)


@router.post(
    "/api/v1/job/{task_type}",
    tags=["job"],
    summary="Create Job",
    description="Creates a new compute job.",
    operation_id="create_job_api_v1_job__task_type__post",
    status_code=status.HTTP_201_CREATED,
    responses={201: {"model": schemas.JobResponse, "description": "Job created"}},
)
async def create_job(
    task_type: str = Path(..., title="Task Type"),
    upload_files: Optional[List[UploadFile]] = File(None),
    external_files: Optional[str] = Form(None),  # JSON array
    priority: int = Form(5),
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(auth.require_permission("ai_inference_support")),
) -> schemas.JobResponse:
    """Create a new compute job."""
    job_service = service.JobService(db)
    return await job_service.create_job(
        task_type=task_type,
        upload_files=upload_files,
        external_files=external_files,
        priority=priority,
        user=user,
    )


@router.get(
    "/api/v1/job/{job_id}",
    tags=["job"],
    summary="Get Job Status",
    description="Get job status and results.",
    operation_id="get_job_api_v1_job__job_id__get",
    responses={200: {"model": schemas.JobResponse, "description": "Job found"}},
)
async def get_job(
    job_id: str = Path(..., title="Job ID"),
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(auth.require_permission("ai_inference_support")),
) -> schemas.JobResponse:
    """Get job status and results."""
    job_service = service.JobService(db)
    return job_service.get_job(job_id)


@router.delete(
    "/api/v1/job/{job_id}",
    tags=["job"],
    summary="Delete Job",
    description="Delete job and all associated files.",
    operation_id="delete_job_api_v1_job__job_id__delete",
    status_code=status.HTTP_200_OK,
)
async def delete_job(
    job_id: str = Path(..., title="Job ID"),
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(auth.require_permission("ai_inference_support")),
):
    """Delete job and all associated files."""
    job_service = service.JobService(db)
    job_service.delete_job(job_id)
    return {}


@router.get(
    "/api/v1/admin/storage/size",
    tags=["admin"],
    summary="Get Storage Size",
    description="Get total storage usage (admin only).",
    operation_id="get_storage_size_api_v1_admin_storage_size_get",
    responses={200: {"model": schemas.StorageInfo, "description": "Storage information"}},
)
async def get_storage_size(
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(auth.require_permission("admin")),
) -> schemas.StorageInfo:
    """Get total storage usage (admin only)."""
    job_service = service.JobService(db)
    return job_service.get_storage_size()


@router.delete(
    "/api/v1/admin/cleanup",
    tags=["admin"],
    summary="Cleanup Old Jobs",
    description="Clean up jobs older than specified number of days (admin only).",
    operation_id="cleanup_old_jobs_api_v1_admin_cleanup_delete",
    responses={200: {"model": schemas.CleanupResult, "description": "Cleanup results"}},
)
async def cleanup_old_jobs(
    days: int = Query(7, ge=0, description="Delete jobs older than N days"),
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(auth.require_permission("admin")),
) -> schemas.CleanupResult:
    """Clean up jobs older than specified number of days (admin only)."""
    job_service = service.JobService(db)
    return job_service.cleanup_old_jobs(days)


class RootResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get(
    "/",
    summary="Health Check",
    description="Returns service health status",
    response_model=RootResponse,
    operation_id="root_get",
)
async def root():
    return RootResponse(
        status="healthy",
        service="CoLAN Store Server",
        version="v1"
    )
