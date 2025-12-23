"""CoLAN Store Server."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import configure_mappers

# CRITICAL: Import versioning BEFORE models
from . import versioning  # noqa: F401
from .compute import (
    close_capability_manager,
    compute_router,
    create_compute_plugin_router,
    get_capability_manager,
)
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


app = FastAPI(title="CoLAN Store", version="v1", lifespan=lifespan)

app.include_router(router)

# Mount compute plugin routes (from cl_ml_tools)
plugin_router, repository_adapter = create_compute_plugin_router()
app.include_router(plugin_router, prefix="/compute", tags=["compute-plugins"])

# Mount compute management routes
app.include_router(compute_router, prefix="/compute", tags=["compute"])


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
