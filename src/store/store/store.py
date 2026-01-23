"""CoLAN Store Server."""

from contextlib import asynccontextmanager

from cl_ml_tools import get_broadcaster
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy.orm import configure_mappers

from store.m_insight.routes import router as intelligence_router

from .monitor import MInsightMonitor
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

    # Initialize MQTT Broadcaster
    config = getattr(app.state, "config", None)
    if config:
        # If mqtt_port is None, get_broadcaster returns NoOpBroadcaster by default if we don't pass broker
        # But we want to be explicit.
        broadcast_type = "mqtt" if config.mqtt_port else "none"
        app.state.broadcaster = get_broadcaster(
            broadcast_type=broadcast_type,
            broker=config.mqtt_server,
            port=config.mqtt_port,
        )
        logger.info(f"MQTT Broadcaster initialized (type={broadcast_type})")
    else:
        app.state.broadcaster = get_broadcaster(broadcast_type="none")
        logger.warning("MQTT Broadcaster initialized as No-Op due to missing config")

    # Initialize MInsight Monitor
    monitor = MInsightMonitor(config)
    monitor.start()
    app.state.monitor = monitor

    logger.info("Store service initialized")

    try:
        yield  # ---- application runs here ----
    finally:
        # -------- Shutdown --------
        monitor = getattr(app.state, "monitor", None)
        if monitor:
             monitor.stop()

        broadcaster = getattr(app.state, "broadcaster", None)
        if broadcaster and hasattr(broadcaster, "disconnect"):
             broadcaster.disconnect()
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
