"""CoLAN Store Server."""

from contextlib import asynccontextmanager
from typing import cast

from cl_ml_tools import BroadcasterBase, get_broadcaster
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy.orm import configure_mappers

from store.m_insight.routes import router as intelligence_router

from .config import StoreConfig
from store.broadcast_service.monitor import MInsightMonitor
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

    # Priority 1: Configuration from app state (set by tests)
    # Priority 2: Configuration from global factory (standard startup)
    if not hasattr(app.state, "config"):
        from .config import get_config
        app.state.config = get_config()
    
    config = cast(StoreConfig, app.state.config)
    logger.info(f"Using configuration with port {config.port}")

    # Initialize MQTT Broadcaster
    config = cast(StoreConfig, getattr(app.state, "config", None))
    if config:
        if not config.mqtt_url:
             raise ValueError("MQTT URL is mandatory for Store service")
             
        from store.broadcast_service.broadcaster import get_insight_broadcaster
        app.state.broadcaster = get_insight_broadcaster(config)
        logger.info(f"MQTT Broadcaster initialized (url={config.mqtt_url})")
    else:
        raise ValueError("Store configuration missing")

    # Initialize MInsight Monitor
    monitor = MInsightMonitor(config)
    monitor.start()
    app.state.monitor = monitor

    logger.info("Store service initialized")

    try:
        yield  # ---- application runs here ----
    finally:
        # -------- Shutdown --------
        monitor = cast(MInsightMonitor, getattr(app.state, "monitor", None))
        if monitor:
            monitor.stop()

        from store.broadcast_service.broadcaster import reset_broadcaster
        reset_broadcaster()
        logger.info("Store service shutdown complete")


app = FastAPI(
    title="CoLAN Store",
    version="v1",
    lifespan=lifespan,
)

app.include_router(router)
app.include_router(intelligence_router, prefix="/intelligence")


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
