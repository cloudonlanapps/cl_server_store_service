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

from . import database
from . import auth, schemas, service
from . import config_service as cfg_service
from .database import get_db
from .service import EntityService


router = APIRouter()


@router.get(
    "/entities",
    tags=["entity"],
    summary="Get Entities",
    description="Retrieves a paginated list of media entities, optionally at a specific version.",
    operation_id="get_entities",
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
    user: Optional[dict] = Depends(auth.require_permission("media_store_read")),
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
    label: Optional[str] = Form(None, title="Label"),
    description: Optional[str] = Form(None, title="Description"),
    parent_id: Optional[int] = Form(None, title="Parent Id"),
    image: Optional[UploadFile] = File(None, title="Image"),
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(auth.require_permission("media_store_write")),
) -> schemas.Item:
    service = EntityService(db)

    # Extract user_id from JWT payload (None in demo mode)
    user_id = user.get("sub") if user else None

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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )


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
    user: Optional[dict] = Depends(auth.require_permission("media_store_write")),
):
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
    version: Optional[int] = Query(
        None, title="Version", description="Optional version number to retrieve"
    ),
    content: Optional[str] = Query(
        None, title="Content", description="Optional content query"
    ),
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(auth.require_permission("media_store_read")),
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
    description: Optional[str] = Form(None, title="Description"),
    parent_id: Optional[int] = Form(None, title="Parent Id"),
    image: Optional[UploadFile] = File(None, title="Image"),
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(auth.require_permission("media_store_write")),
) -> schemas.Item:
    service = EntityService(db)

    # Extract user_id from JWT payload (None in demo mode)
    user_id = user.get("sub") if user else None

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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )


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
    entity_id: int,
    body: schemas.BodyPatchEntity = Body(..., embed=True),
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(auth.require_permission("media_store_write")),
) -> schemas.Item:
    service = EntityService(db)

    # Extract user_id from JWT payload (None in demo mode)
    user_id = user.get("sub") if user else None

    item = service.patch_entity(entity_id, body, user_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found"
        )
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
    user: Optional[dict] = Depends(auth.require_permission("media_store_write")),
):
    service = EntityService(db)
    item = service.delete_entity(entity_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found"
        )
    # No return statement - FastAPI will return 204 automatically


@router.get(
    "/entities/{entity_id}/versions",
    tags=["entity"],
    summary="Get Entity Versions",
    description="Retrieves all versions of a specific entity.",
    operation_id="get_entity_versions",
    responses={200: {"model": List[dict], "description": "Successful Response"}},
)
async def get_entity_versions(
    entity_id: int = Path(..., title="Entity Id"),
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(auth.require_permission("media_store_read")),
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
    user: Optional[dict] = Depends(auth.require_admin),
) -> schemas.ConfigResponse:
    """Get current service configuration.

    Requires admin access.
    """

    config_service = cfg_service.ConfigService(db)

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
    user: Optional[dict] = Depends(auth.require_admin),
) -> dict:
    """Update read authentication configuration.

    Requires admin access. Changes are persistent and take effect immediately.
    """

    from .config_service import ConfigService

    config_service = ConfigService(db)

    # Get user ID from JWT
    user_id = user.get("sub") if user else None

    # Update configuration
    config_service.set_read_auth_enabled(config.enabled, user_id)

    return {
        "read_auth_enabled": config.enabled,
        "message": "Configuration updated successfully",
    }


# Job Management Endpoints (from compute service)


@router.get(
    "/compute/jobs/{job_id}",
    tags=["job"],
    summary="Get Job Status",
    description="Get job status and results.",
    operation_id="get_job",
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
    "/compute/jobs/{job_id}",
    tags=["job"],
    summary="Delete Job",
    description="Delete job and all associated files.",
    operation_id="delete_job",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_job(
    job_id: str = Path(..., title="Job ID"),
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(auth.require_permission("ai_inference_support")),
):
    """Delete job and all associated files."""
    job_service = service.JobService(db)
    job_service.delete_job(job_id)
    # No return statement - FastAPI will return 204 automatically


@router.get(
    "/admin/compute/jobs/storage/size",
    tags=["admin"],
    summary="Get Storage Size",
    description="Get total storage usage (admin only).",
    operation_id="get_storage_size",
    responses={
        200: {"model": schemas.StorageInfo, "description": "Storage information"}
    },
)
async def get_storage_size(
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(auth.require_admin),
) -> schemas.StorageInfo:
    """Get total storage usage (admin only)."""
    job_service = service.JobService(db)
    return job_service.get_storage_size()


@router.delete(
    "/admin/compute/jobs/cleanup",
    tags=["admin"],
    summary="Cleanup Old Jobs",
    description="Clean up jobs older than specified number of days (admin only).",
    operation_id="cleanup_old_jobs",
    responses={200: {"model": schemas.CleanupResult, "description": "Cleanup results"}},
)
async def cleanup_old_jobs(
    days: int = Query(7, ge=0, description="Delete jobs older than N days"),
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(auth.require_admin),
) -> schemas.CleanupResult:
    """Clean up jobs older than specified number of days (admin only)."""
    job_service = service.JobService(db)
    return job_service.cleanup_old_jobs(days)


@router.get(
    "/compute/capabilities",
    tags=["compute"],
    summary="Get Worker Capabilities",
    description="Returns available worker capabilities and their available counts",
    response_model=dict,
    operation_id="get_worker_capabilities",
)
async def get_worker_capabilities(
    db: Session = Depends(get_db),
) -> dict:
    """Get available worker capabilities and counts from connected workers.

    Returns a dictionary with:
    - num_workers: Total number of connected workers (0 if none available)
    - capabilities: Dictionary mapping capability names to available worker counts

    Example response:
    {
        "num_workers": 3,
        "capabilities": {
            "image_resize": 2,
            "image_conversion": 1
        }
    }
    """
    capability_service = service.CapabilityService(db)
    capabilities = capability_service.get_available_capabilities()
    num_workers = capability_service.get_worker_count()
    return {
        "num_workers": num_workers,
        "capabilities": capabilities,
    }


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
    return RootResponse(status="healthy", service="CoLAN Store Server", version="v1")
