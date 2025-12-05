"""CoLAN Store Server."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import configure_mappers

# CRITICAL: Import versioning BEFORE models
from . import versioning  # noqa: F401
from .mqtt_client import close_mqtt_client, get_mqtt_client
from .routes import router

# Import for cl_media_tools integration
from cl_media_tools.master import create_master_router
from cl_server_shared.adapters import SQLAlchemyJobRepository, FileStorageAdapter
from cl_server_shared.file_storage import FileStorageService
from cl_server_shared.config import MEDIA_STORAGE_DIR
from .database import SessionLocal
from .auth import require_permission

logger = logging.getLogger(__name__)

# Configure mappers after all models are imported (required for versioning)
configure_mappers()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifecycle - startup and shutdown hooks."""
    # Startup
    logger.info("Initializing MQTT client for worker capability discovery")
    try:
        mqtt_client = get_mqtt_client()
        if mqtt_client.wait_for_capabilities(timeout=5):
            logger.info("MQTT client ready and subscribed to worker capabilities")
        else:
            logger.warning("MQTT client connection timeout - proceeding with empty capabilities")
    except Exception as e:
        logger.error(f"Failed to initialize MQTT client: {e}")

    yield

    # Shutdown
    logger.info("Closing MQTT client")
    try:
        close_mqtt_client()
        logger.info("MQTT client closed")
    except Exception as e:
        logger.error(f"Error closing MQTT client: {e}")


app = FastAPI(title="CoLAN server", version="v1", lifespan=lifespan)

app.include_router(router)

# Mount cl_media_tools plugin routes
# Create adapter instances
repository_adapter = SQLAlchemyJobRepository(SessionLocal)
file_storage_service = FileStorageService(base_dir=MEDIA_STORAGE_DIR)
file_storage_adapter = FileStorageAdapter(file_storage_service)

# Create and mount plugin router
# NOTE: We pass require_permission("ai_inference_support") instead of get_current_user
# This enforces proper authentication and authorization for plugin routes
plugin_router = create_master_router(
    repository=repository_adapter,
    file_storage=file_storage_adapter,
    get_current_user=require_permission("ai_inference_support")
)
app.include_router(plugin_router, prefix="/compute", tags=["compute-plugins"])



@app.exception_handler(HTTPException)
async def validation_exception_handler(request: Request, exc: HTTPException):
    """
    Preserve the default FastAPI HTTPException handling shape so callers
    can rely on the same error response structure.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )
