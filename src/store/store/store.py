"""CoLAN Store Server."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy.orm import configure_mappers

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
    
    # Try to get config from app state (injected by main.py or tests)
    if hasattr(app.state, "config") and app.state.config:
        logger.info("Loaded core configuration from app.state.config")
    else:
        # Fallback for dev/test if config not injected
        logger.warning("No config found in app.state.config. Using default.")

    logger.info("Store service initialized")

    try:
        yield  # ---- application runs here ----
    finally:
        # -------- Shutdown --------
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
