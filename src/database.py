from __future__ import annotations

# CRITICAL: Import versioning BEFORE models to ensure make_versioned() is called first
from . import versioning  # noqa: F401

from cl_server_shared import create_db_engine, create_session_factory, get_db_session
from cl_server_shared.config import STORE_DATABASE_URL as DATABASE_URL

# Create engine with WAL mode (handled by cl_server_shared)
engine = create_db_engine(DATABASE_URL, echo=False)
SessionLocal = create_session_factory(engine)


def get_db():
    """Get database session for FastAPI dependency injection."""
    yield from get_db_session(SessionLocal)
