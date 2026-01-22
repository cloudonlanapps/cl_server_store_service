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
import json
import time
from pydantic import BaseModel
from loguru import logger
from sqlalchemy.orm import Session

from . import config_service as cfg_service
from ..common import models, schemas
from ..common.auth import UserPayload, require_admin, require_permission
from ..common.database import SessionLocal, get_db
from .service import EntityService
from .config import StoreConfig

router = APIRouter()




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
    request: Request = None,  # pyright: ignore[reportGeneralTypeIssues]
) -> schemas.PaginatedResponse:
    """
    Get all entities with pagination.
    """
    _ = user
    config: StoreConfig = request.app.state.config
    service = EntityService(db, config)
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
    request: Request = None,  # pyright: ignore[reportGeneralTypeIssues]
) -> schemas.Item:
    config: StoreConfig = request.app.state.config
    service = EntityService(db, config)

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
        item, is_duplicate = service.create_entity(body, file_bytes, filename, user_id)

        # Broadcast MQTT event only if this was a new entity (not a duplicate)
        broadcaster = getattr(request.app.state, "broadcaster", None)
        if broadcaster and item.md5 and not is_duplicate:
            topic = f"store/{config.port}/items"
            payload = {
                "id": item.id,
                "md5": item.md5,
                "timestamp": int(time.time() * 1000)
            }
            broadcaster.publish_event(topic=topic, payload=json.dumps(payload))
            logger.info(f"Broadcasted creation event for item {item.id} on {topic}")

        # Trigger async jobs for images (NON-BLOCKING)
    
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
    request: Request = None,  # pyright: ignore[reportGeneralTypeIssues]
):
    _ = user
    config: StoreConfig = request.app.state.config
    service = EntityService(db, config)
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
    request: Request = None,  # pyright: ignore[reportGeneralTypeIssues]
) -> schemas.Item:
    _ = user
    config: StoreConfig = request.app.state.config
    service = EntityService(db, config)
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
    request: Request = None,  # pyright: ignore[reportGeneralTypeIssues]
) -> schemas.Item:
    config: StoreConfig = request.app.state.config
    service = EntityService(db, config)

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
        result = service.update_entity(entity_id, body, file_bytes, filename, user_id)
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
        
        item, is_duplicate = result

        # Broadcast MQTT event only if file was actually updated (not a duplicate)
        # Note: Broadcaster only emits if a file was actually updated (item.md5 is not None for media)
        broadcaster = getattr(request.app.state, "broadcaster", None)
        if broadcaster and item.md5 and image and not is_duplicate:
            topic = f"store/{config.port}/items"
            payload = {
                "id": item.id,
                "md5": item.md5,
                "timestamp": int(time.time() * 1000)
            }
            broadcaster.publish_event(topic=topic, payload=json.dumps(payload))
            logger.info(f"Broadcasted update event for item {item.id} on {topic}")

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
    config: StoreConfig = request.app.state.config
    service = EntityService(db, config)

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
    request: Request = None,  # pyright: ignore[reportGeneralTypeIssues]
):
    _ = user
    config: StoreConfig = request.app.state.config
    service = EntityService(db, config)
    
    # Delete entity (will raise ValueError if not soft-deleted first)
    deleted = service.delete_entity(entity_id)
    if not deleted:
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
    request: Request = None,  # pyright: ignore[reportGeneralTypeIssues]
) -> list[dict[str, int | None]]:
    _ = user
    config: StoreConfig = request.app.state.config
    service = EntityService(db, config)
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


@router.get(
    "/m_insight/status",
    tags=["admin"],
    summary="Get MInsight Status",
    description="Get current status of MInsight processes.",
    operation_id="get_m_insight_status",
)
async def get_m_insight_status(request: Request) -> dict:
    """Get MInsight process status."""
    if hasattr(request.app.state, "monitor"):
        return request.app.state.monitor.get_status()
    # Logic to return default/offline status if monitor is not present (e.g. during tests)
    # The monitor is initialized in lifespan, but if mqtt_port is None, it might be running but disconnected?
    # Actually monitor.start() checks mqtt_port. 
    # If monitor is present but empty, it returns {}.
    return {}


