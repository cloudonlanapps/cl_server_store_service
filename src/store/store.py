"""CoLAN Store Server."""

import logging
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import configure_mappers

from .pysdk_config import PySDKRuntimeConfig
from .routes import router

logger = logging.getLogger(__name__)

# Configure mappers after all models are imported (required for versioning)
configure_mappers()


app = FastAPI(title="CoLAN Store", version="v1")

app.include_router(router)


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize services on startup."""
    # Load PySDK configuration from environment (set by main.py)
    config_json = os.getenv("PYSDK_CONFIG_JSON")
    if config_json:
        app.state.pysdk_config = PySDKRuntimeConfig.model_validate_json(config_json)
    else:
        # Fallback to defaults if not provided
        app.state.pysdk_config = PySDKRuntimeConfig()
        logger.warning("No PYSDK_CONFIG_JSON found, using default configuration")

    logger.info(f"Loaded PySDK config: compute={app.state.pysdk_config.compute_service_url}")

    from .compute_singleton import async_get_compute_client
    from .face_store_singleton import get_face_store
    from .qdrant_singleton import get_qdrant_store

    _ = await async_get_compute_client(app.state.pysdk_config)  # Initialize MQTT connection with auth
    _ = get_qdrant_store(app.state.pysdk_config)  # Initialize Qdrant collection for CLIP embeddings
    _ = get_face_store(app.state.pysdk_config)  # Initialize Qdrant collection for face embeddings
    logger.info("Store service initialized with async job processing")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Cleanup on shutdown."""
    from .compute_singleton import shutdown_compute_client

    await shutdown_compute_client()
    logger.info("Store service shutdown complete")


@app.exception_handler(HTTPException)
async def validation_exception_handler(_request: Request, exc: HTTPException):
    """
    Preserve the default FastAPI HTTPException handling shape so callers
    can rely on the same error response structure.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )
