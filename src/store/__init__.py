"""CoLAN Store Server."""

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import configure_mappers

# CRITICAL: Import versioning BEFORE models
from . import versioning  # noqa: F401
from .routes import router

logger = logging.getLogger(__name__)

# Configure mappers after all models are imported (required for versioning)
configure_mappers()


app = FastAPI(title="CoLAN Store", version="v1")

app.include_router(router)


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
