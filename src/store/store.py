"""CoLAN Store Server."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import configure_mappers

from .pysdk_config import PySDKRuntimeConfig
from .routes import router

logger = logging.getLogger(__name__)

# Configure mappers after all models are imported (required for versioning)
configure_mappers()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler:
    - Startup: initialize services and connections
    - Shutdown: cleanup resources
    """
    # -------- Startup --------
    config_json = os.getenv("PYSDK_CONFIG_JSON")
    if config_json:
        app.state.pysdk_config = PySDKRuntimeConfig.model_validate_json(config_json)
    else:
        app.state.pysdk_config = PySDKRuntimeConfig()
        logger.warning("No PYSDK_CONFIG_JSON found, using default configuration")

    logger.info(
        "Loaded PySDK config: compute=%s",
        app.state.pysdk_config.compute_service_url,
    )

    from .compute_singleton import async_get_compute_client
    from .face_store_singleton import get_face_store
    from .qdrant_singleton import get_qdrant_store

    _ = await async_get_compute_client(app.state.pysdk_config)
    _ = get_qdrant_store(app.state.pysdk_config)
    _ = get_face_store(app.state.pysdk_config)

    logger.info("Store service initialized with async job processing")

    try:
        yield  # ---- application runs here ----
    finally:
        # -------- Shutdown --------
        from .compute_singleton import shutdown_compute_client

        await shutdown_compute_client()
        logger.info("Store service shutdown complete")


app = FastAPI(
    title="CoLAN Store",
    version="v1",
    lifespan=lifespan,
)

app.include_router(router)


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
