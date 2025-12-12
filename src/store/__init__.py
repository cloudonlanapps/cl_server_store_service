"""CoLAN Store Server."""

import logging
from contextlib import asynccontextmanager

# Import for cl_ml_tools integration
from cl_ml_tools import create_master_router
from cl_server_shared.config import Config
from cl_server_shared.file_storage import FileStorageService
from cl_server_shared.shared_db import SQLAlchemyJobRepository
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import configure_mappers

# CRITICAL: Import versioning BEFORE models
from . import versioning  # noqa: F401
from .auth import require_permission
from .capability_manager import close_capability_manager, get_capability_manager
from .database import SessionLocal
from .routes import router

logger = logging.getLogger(__name__)

# Configure mappers after all models are imported (required for versioning)
configure_mappers()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifecycle - startup and shutdown hooks."""
    # Startup
    logger.info("Initializing capability manager for worker discovery")
    try:
        manager = get_capability_manager()
        if manager.wait_for_capabilities(timeout=5):
            logger.info("Capability manager ready and subscribed to workers")
        else:
            logger.warning(
                "Capability manager timeout - proceeding with empty capabilities"
            )
    except Exception as e:
        logger.error(f"Failed to initialize capability manager: {e}")

    yield

    # Shutdown
    logger.info("Closing capability manager")
    try:
        close_capability_manager()
        logger.info("Capability manager closed")
    except Exception as e:
        logger.error(f"Error closing capability manager: {e}")


app = FastAPI(title="CoLAN server", version="v1", lifespan=lifespan)

app.include_router(router)

# Mount cl_ml_tools plugin routes
# Create adapter instances
repository_adapter = SQLAlchemyJobRepository(SessionLocal)
file_storage_service = FileStorageService(base_dir=Config.MEDIA_STORAGE_DIR)

# Create and mount plugin router
# NOTE: We pass require_permission("ai_inference_support") instead of get_current_user
# This enforces proper authentication and authorization for plugin routes
plugin_router = create_master_router(
    repository=repository_adapter,
    file_storage=file_storage_service,
    get_current_user=require_permission("ai_inference_support"),
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
