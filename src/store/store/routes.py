from __future__ import annotations

import json
import math
import time
from typing import cast

from cl_ml_tools import BroadcasterBase
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from loguru import logger
from pydantic import BaseModel

from store.db_service.config import ConfigDBService
from store.db_service.db_internals import get_db
from sqlalchemy.orm import Session

from store.db_service import EntitySchema
from store.db_service import schemas as db_schemas
from ..broadcast_service import schemas as broadcast_schemas
from ..common.auth import UserPayload, require_admin, require_permission
from .dependencies import get_broadcaster, get_config_service, get_entity_service, get_monitor
from .config import get_config as arg_config
from store.vectorstore_services.vector_stores import (
    QdrantVectorStore,
    get_clip_store_dep,
    get_dino_store_dep,
    get_face_store_dep,
)
from ..broadcast_service.monitor import MInsightMonitor
from .service import DuplicateFileError, EntityService, EntityNotSoftDeletedError
from .audit_service import AuditReport, AuditService, CleanupReport
from .config import StoreConfig
from ..common.storage import StorageService

router = APIRouter()


@router.get(
    "/entities",
    tags=["entity"],
    summary="Get Entities",
    description="Retrieves a paginated list of media entities, optionally at a specific version.",
    operation_id="get_entities",
    responses={200: {"model": db_schemas.PaginatedResponse, "description": "Successful Response"}},
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
    user: UserPayload | None = Depends(require_permission("media_store_read")),
    service: EntityService = Depends(get_entity_service),
) -> db_schemas.PaginatedResponse:
    """
    Get all entities with pagination.
    """
    _ = user
    items, total_count = service.get_entities(
        page=page,
        page_size=page_size,
        version=version,
        filter_param=filter_param,
        search_query=search_query,
        exclude_deleted=exclude_deleted,
    )

    # Calculate pagination metadata

    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0
    has_next = page < total_pages
    has_prev = page > 1

    pagination = db_schemas.PaginationMetadata(
        page=page,
        page_size=page_size,
        total_items=total_count,
        total_pages=total_pages,
        has_next=has_next,
        has_prev=has_prev,
    )

    return db_schemas.PaginatedResponse(items=items, pagination=pagination)


@router.post(
    "/entities",
    tags=["entity"],
    summary="Create Entity",
    description="Creates a new entity.",
    operation_id="create_entity",
    status_code=status.HTTP_201_CREATED,
    responses={201: {"model": EntitySchema, "description": "Successful Response"}},
)
async def create_entity(
    response: Response,
    is_collection: bool = Form(..., title="Is Collection"),
    label: str | None = Form(None, title="Label"),
    description: str | None = Form(None, title="Description"),
    parent_id: int | None = Form(None, title="Parent Id"),
    image: UploadFile | None = File(None, title="Image"),
    user: UserPayload | None = Depends(require_permission("media_store_write")),
    service: EntityService = Depends(get_entity_service),
    broadcaster: BroadcasterBase | None = Depends(get_broadcaster),
) -> EntitySchema:
    config = service.config

    # Extract user_id from JWT payload (None in demo mode)
    user_id = user.id if user else None

    # Read file bytes and filename if provided
    file_bytes = None
    filename = "file"
    if image:
        file_bytes = await image.read()
        filename = image.filename or "file"

    try:
        item, is_duplicate = service.create_entity(
            is_collection=is_collection,
            label=label,
            description=description,
            parent_id=parent_id,
            image=file_bytes,
            filename=filename,
            user_id=user_id
        )

        if is_duplicate:
            response.status_code = status.HTTP_200_OK
        else:
            response.status_code = status.HTTP_201_CREATED

        # CRITICAL: Clear retained MQTT status to prevent "ghost" statuses from ID reuse
        if broadcaster:
            status_topic = f"mInsight/{config.port}/entity_item_status/{item.id}"
            _ = broadcaster.clear_retained(status_topic)
            logger.debug(f"Cleared retained status for entity {item.id} on {status_topic}")

        # Broadcast MQTT event only if this was a new entity (not a duplicate)
        if broadcaster and item.md5 and not is_duplicate:
            topic = f"store/{config.port}/items"
            payload = {"id": item.id, "md5": item.md5, "timestamp": int(time.time() * 1000)}
            _ = broadcaster.publish_event(topic=topic, payload=json.dumps(payload))
            logger.info(f"Broadcasted creation event for item {item.id} on {topic}")

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





@router.get(
    "/entities/{entity_id}",
    tags=["entity"],
    summary="Get Entity",
    description="Retrieves a specific media entity by its ID, optionally at a specific version.",
    operation_id="get_entity",
    responses={200: {"model": EntitySchema, "description": "Successful Response"}},
)
async def get_entity(
    entity_id: int = Path(..., title="Entity Id"),
    version: int | None = Query(
        None, title="Version", description="Optional version number to retrieve"
    ),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
    service: EntityService = Depends(get_entity_service),
) -> EntitySchema:
    _ = user
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
    responses={200: {"model": EntitySchema, "description": "Successful Response"}},
)
async def put_entity(
    entity_id: int = Path(..., title="Entity Id"),
    is_collection: bool = Form(..., title="Is Collection"),
    label: str = Form(..., title="Label"),
    description: str | None = Form(None, title="Description"),
    parent_id: int | None = Form(None, title="Parent Id"),
    image: UploadFile | None = File(None, title="Image"),
    user: UserPayload | None = Depends(require_permission("media_store_write")),
    service: EntityService = Depends(get_entity_service),
    broadcaster: BroadcasterBase | None = Depends(get_broadcaster),
) -> EntitySchema:
    config = service.config

    # Extract user_id from JWT payload (None in demo mode)
    user_id = user.id if user else None

    # Read file bytes and filename if provided
    file_bytes: bytes | None = None
    filename = "file"
    if image:
        file_bytes = await image.read()
        filename = image.filename or "file"

    try:
        # Update entity (file is optional - None updates only metadata)
        result = service.update_entity(
            entity_id=entity_id,
            is_collection=is_collection,
            label=label,
            description=description,
            parent_id=parent_id,
            image=file_bytes,
            filename=filename,
            user_id=user_id,
        )
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")

        item, _ = result

        # CRITICAL: Clear retained MQTT status if we are updating with a new file (re-processing)
        if broadcaster and image:
            status_topic = f"mInsight/{config.port}/entity_item_status/{item.id}"
            _ = broadcaster.clear_retained(status_topic)
            logger.debug(f"Cleared retained status for entity {item.id} on {status_topic}")

        # Broadcast MQTT event only if file was actually updated
        # Note: Broadcaster only emits if file was updated (item.md5 not None for media)
        if broadcaster and item.md5 and image:
            topic = f"store/{config.port}/items"
            payload = {"id": item.id, "md5": item.md5, "timestamp": int(time.time() * 1000)}
            _ = broadcaster.publish_event(topic=topic, payload=json.dumps(payload))
            logger.info(f"Broadcasted update event for item {item.id} on {topic}")

        return item
    except DuplicateFileError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        # Validation errors or invalid file format
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
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
    description=(
        "Partially updates an entity. Use this endpoint to soft delete (is_deleted=true) "
        "or restore (is_deleted=false) an entity."
    ),
    operation_id="patch_entity",
    responses={
        200: {"model": EntitySchema, "description": "Successful Response"},
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
    user: UserPayload | None = Depends(require_permission("media_store_write")),
    service: EntityService = Depends(get_entity_service),
) -> EntitySchema:
    # Extract user_id from JWT payload (None in demo mode)
    user_id = user.id if user else None

    # Get raw form data to check if fields with empty values were actually sent
    form_data = await request.form()
    form_keys = set(form_data.keys())

    # Create body object from form fields
    # Handle type conversions for form data (strings to proper types)
    patch_data = {}
    _ = label
    if "label" in form_keys:
        label_val = form_data.get("label")
        patch_data["label"] = label_val if label_val != "" else None
    _ = description
    if "description" in form_keys:
        description_val = form_data.get("description")
        patch_data["description"] = description_val if description_val != "" else None
    # Check if parent_id was actually sent (even as empty string)
    _ = parent_id
    if "parent_id" in form_keys:
        # Empty string means set to None, otherwise parse as int
        parent_id_val = form_data.get("parent_id")
        if isinstance(parent_id_val, str) and parent_id_val != "":
            patch_data["parent_id"] = int(parent_id_val)
        else:
            patch_data["parent_id"] = None
    # Check if is_deleted was actually sent
    _ = is_deleted
    if "is_deleted" in form_keys:
        # Convert string boolean to actual boolean
        is_deleted_val = form_data.get("is_deleted")
        if isinstance(is_deleted_val, str):
            patch_data["is_deleted"] = is_deleted_val.lower() in ("true", "1", "yes")

            patch_data["is_deleted"] = is_deleted_val.lower() in ("true", "1", "yes")

    # Use model_construct to preserve explicit None values as "set"
    # Actually for service call we just pass the dict as changes
    changes = cast(dict[str, object], patch_data)

    item = service.patch_entity(entity_id, changes=changes, user_id=user_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    return item





@router.get(
    "/entities/{entity_id}/versions",
    tags=["entity"],
    summary="Get Entity Versions",
    description="Retrieves all versions of a specific entity.",
    operation_id="get_entity_versions",
    response_model=list[db_schemas.VersionInfo],
)
async def get_entity_versions(
    entity_id: int = Path(..., title="Entity Id"),
    user: UserPayload | None = Depends(require_permission("media_store_read")),
    service: EntityService = Depends(get_entity_service),
) -> list[db_schemas.VersionInfo]:
    _ = user
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
    responses={200: {"model": db_schemas.ConfigResponse, "description": "Successful Response"}},
)
async def get_config(
    user: UserPayload | None = Depends(require_admin),
    config_service: ConfigDBService = Depends(get_config_service),
) -> db_schemas.ConfigResponse:
    """Get current service configuration.

    Requires admin access.
    """
    _ = user

    # Get config metadata
    metadata = config_service.get_config_metadata("read_auth_enabled")

    if metadata:
        value_str = str(metadata["value"]) if metadata["value"] is not None else "false"
        updated_at = metadata["updated_at"]
        updated_by = metadata["updated_by"]
        # Invert logic: read_auth_enabled=false means guest_mode=true
        read_auth_enabled = value_str.lower() == "true"
        return db_schemas.ConfigResponse(
            guest_mode=not read_auth_enabled,
            updated_at=int(updated_at)
            if updated_at is not None and not isinstance(updated_at, str)
            else None,
            updated_by=str(updated_by)
            if updated_by is not None and not isinstance(updated_by, int)
            else None,
        )

    # Default if not found: read_auth_enabled=false means guest_mode=true
    return db_schemas.ConfigResponse(guest_mode=True, updated_at=None, updated_by=None)


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
    user: UserPayload | None = Depends(require_admin),
    config_service: ConfigDBService = Depends(get_config_service),
) -> dict[str, bool | str]:
    """Update guest mode configuration.

    Requires admin access. Changes are persistent and take effect immediately.
    guest_mode=true means no authentication required.
    guest_mode=false means authentication required.
    """

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
async def root(config_service: ConfigDBService = Depends(get_config_service)):
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
    description="Get current status of MInsight processes for the configured port.",
    operation_id="get_m_insight_status",
    response_model=broadcast_schemas.MInsightStatus | None,
)
async def get_m_insight_status(
    monitor: MInsightMonitor | None = Depends(get_monitor),
) -> broadcast_schemas.MInsightStatus | None:
    """Get MInsight process status."""
    if monitor:
        return monitor.get_status()
    return None


# ============================================================================
# Deletion & Audit Endpoints (DEL-01 to DEL-10)
# ============================================================================


@router.delete(
    "/entities/{entity_id}",
    tags=["entity"],
    summary="Delete Entity (Hard Delete)",
    description="""Permanently delete an entity with full cleanup of all associated resources.

    Requirements (DEL-09):
    - Entity MUST be soft-deleted first (is_deleted=True) before hard deletion
    - Use PATCH /entities/{id} with is_deleted=true to soft-delete first

    This operation:
    - Deletes all faces (DB + vectors + files)
    - Deletes CLIP/DINO embeddings
    - Deletes entity file
    - Clears MQTT retained messages
    - Removes entity from database
    - For collections: recursively deletes all children (soft-deleting them first if needed)
    """,
    operation_id="delete_entity",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Entity successfully deleted"},
        404: {"description": "Entity not found"},
        400: {"description": "Entity not soft-deleted (DEL-09 violation)"},
    },
)
async def delete_entity(
    entity_id: int = Path(..., description="Entity ID to delete"),
    user: UserPayload | None = Depends(require_permission("media_store_write")),
    service: EntityService = Depends(get_entity_service),
) -> Response:
    """Delete an entity permanently (DEL-01 to DEL-06, DEL-09)."""
    _ = user

    try:
        deleted = service.delete_entity(entity_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Entity {entity_id} not found",
            )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except EntityNotSoftDeletedError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to delete entity {entity_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete entity: {str(e)}",
        )


@router.delete(
    "/faces/{face_id}",
    tags=["face"],
    summary="Delete Face",
    description="""Delete a face completely (DB + vector + file) and update entity face_count.

    This operation (DEL-08):
    - Removes face record from database
    - Deletes face embedding from vector store
    - Deletes face crop image file
    - Decrements face_count in parent entity intelligence_data
    """,
    operation_id="delete_face",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Face successfully deleted"},
        404: {"description": "Face not found"},
    },
)
async def delete_face(
    face_id: int = Path(..., description="Face ID to delete"),
    user: UserPayload | None = Depends(require_permission("media_store_write")),
    service: EntityService = Depends(get_entity_service),
) -> Response:
    """Delete a face and update entity face_count (DEL-08)."""
    _ = user

    try:
        deleted = service.face_service.delete_face(face_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Face {face_id} not found",
            )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except Exception as e:
        logger.error(f"Failed to delete face {face_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete face: {str(e)}",
        )


@router.get(
    "/system/audit",
    tags=["admin"],
    summary="Audit Data Integrity",
    description="""Generate a comprehensive audit report of data integrity issues.

    This endpoint performs readonly checks for:
    - Orphaned files in storage without DB entities
    - Orphaned Face records without valid entity references
    - Orphaned vectors in Qdrant without DB entities
    - Orphaned MQTT retained messages (if broadcaster available)

    No data is modified by this operation.
    """,
    operation_id="audit_system",
    response_model=AuditReport,
)
async def audit_system(
    db: Session = Depends(get_db),
    config: StoreConfig = Depends(arg_config),
    clip_store: QdrantVectorStore = Depends(get_clip_store_dep),
    dino_store: QdrantVectorStore = Depends(get_dino_store_dep),
    face_store: QdrantVectorStore = Depends(get_face_store_dep),
    broadcaster: BroadcasterBase | None = Depends(get_broadcaster),
    user: UserPayload | None = Depends(require_admin),
) -> AuditReport:
    """Generate data integrity audit report."""
    _ = user

    # Create storage service
    storage_service = StorageService(base_dir=str(config.media_storage_dir))

    # Create audit service
    audit_service = AuditService(
        db=db,
        storage_service=storage_service,
        clip_store=clip_store,
        dino_store=dino_store,
        face_store=face_store,
        broadcaster=broadcaster,
    )

    # Generate report
    report = audit_service.generate_report()
    return report


@router.post(
    "/system/clear-orphans",
    tags=["admin"],
    summary="Clear Orphaned Resources",
    description="""Remove all orphaned resources identified by the audit system (DEL-10).

    This endpoint:
    1. Runs an audit to identify orphaned resources
    2. Deletes orphaned files from storage
    3. Removes orphaned Face records from database
    4. Deletes orphaned vectors from Qdrant
    5. Clears orphaned MQTT retained messages

    Returns a summary of cleaned resources.
    """,
    operation_id="clear_orphans",
    response_model=CleanupReport,
)
async def clear_orphans(
    db: Session = Depends(get_db),
    config: StoreConfig = Depends(arg_config),
    clip_store: QdrantVectorStore = Depends(get_clip_store_dep),
    dino_store: QdrantVectorStore = Depends(get_dino_store_dep),
    face_store: QdrantVectorStore = Depends(get_face_store_dep),
    broadcaster: BroadcasterBase | None = Depends(get_broadcaster),
    user: UserPayload | None = Depends(require_admin),
) -> CleanupReport:
    """Clear all orphaned resources (DEL-10)."""
    _ = user

    # Create storage service
    storage_service = StorageService(base_dir=str(config.media_storage_dir))

    try:
        # Create audit service
        audit_service = AuditService(
            db=db,
            storage_service=storage_service,
            clip_store=clip_store,
            dino_store=dino_store,
            face_store=face_store,
            broadcaster=broadcaster,
        )

        # Generate audit report
        logger.info("Generating audit report before cleanup...")
        report = audit_service.generate_report()

        cleanup_report = CleanupReport()

        # Delete orphaned files
        logger.info(f"Deleting {len(report.orphaned_files)} orphaned files...")
        for orphan in report.orphaned_files:
            try:
                storage_service.delete_file(orphan.file_path)
                cleanup_report.files_deleted += 1
            except Exception as e:
                logger.warning(f"Failed to delete orphaned file {orphan.file_path}: {e}")

        # Delete orphaned face records
        logger.info(f"Deleting {len(report.orphaned_faces)} orphaned face records...")
        from store.db_service.db_internals import Face
        for orphan in report.orphaned_faces:
            try:
                face = db.query(Face).filter(Face.id == orphan.face_id).first()
                if face:
                    db.delete(face)
                    cleanup_report.faces_deleted += 1
            except Exception as e:
                logger.warning(f"Failed to delete orphaned face {orphan.face_id}: {e}")

        db.commit()

        # Delete orphaned vectors
        logger.info(f"Deleting {len(report.orphaned_vectors)} orphaned vectors...")
        for orphan in report.orphaned_vectors:
            try:
                if orphan.collection_name == "clip_embeddings":
                    clip_store.delete_vector(orphan.vector_id)
                    cleanup_report.vectors_deleted += 1
                elif orphan.collection_name == "dino_embeddings":
                    dino_store.delete_vector(orphan.vector_id)
                    cleanup_report.vectors_deleted += 1
                elif orphan.collection_name == "face_embeddings":
                    face_store.delete_vector(orphan.vector_id)
                    cleanup_report.vectors_deleted += 1
            except Exception as e:
                logger.warning(f"Failed to delete orphaned vector {orphan.vector_id}: {e}")

        # Clear orphaned MQTT messages
        if broadcaster and report.orphaned_mqtt:
            logger.info(f"Clearing {len(report.orphaned_mqtt)} orphaned MQTT messages...")
            for orphan in report.orphaned_mqtt:
                try:
                    broadcaster.clear_entity_status(orphan.entity_id)
                    cleanup_report.mqtt_cleared += 1
                except Exception as e:
                    logger.warning(f"Failed to clear MQTT for entity {orphan.entity_id}: {e}")

        logger.info(
            f"Cleanup complete: {cleanup_report.files_deleted} files, "
            f"{cleanup_report.faces_deleted} faces, {cleanup_report.vectors_deleted} vectors, "
            f"{cleanup_report.mqtt_cleared} MQTT messages"
        )

        return cleanup_report

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to clear orphans: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear orphans: {str(e)}",
        )
