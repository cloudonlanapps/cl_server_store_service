"""CoLAN Store Server."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy.orm import configure_mappers

from .pysdk_config import PySDKRuntimeConfig
from .routes import router

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
    # -------- Startup --------
    
    # Try to get config from app state (injected by main.py or tests)
    if hasattr(app.state, "config") and app.state.config:
        app.state.pysdk_config = app.state.config.pysdk_config
        logger.info("Loaded configuration from app.state.config")
    else:
        # Fallback to environment variables (legacy/dev support)
        # Note: This path should ideally be removed once migration is complete and consistent
        config_json = os.getenv("PYSDK_CONFIG_JSON")
        if config_json:
            app.state.pysdk_config = PySDKRuntimeConfig.model_validate_json(config_json)
        else:
            app.state.pysdk_config = PySDKRuntimeConfig()
            logger.warning("No config found in app.state or environment, using default defaults")

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


@app.exception_handler(ValueError)
async def value_error_handler(_request: Request, exc: ValueError):
    """
    Handle ValueError as 422 Unprocessable Entity.
    Commonly used for business logic validation errors in service layer.
    """
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc)},
    )
