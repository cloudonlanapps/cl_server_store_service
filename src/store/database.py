"""Database configuration with WAL mode support for multi-process access."""

from __future__ import annotations

from typing import Generator

from cl_server_shared.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# CRITICAL: Import versioning BEFORE models to ensure make_versioned() is called first
from . import versioning  # noqa: F401  # pyright: ignore[reportUnusedImport]


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


def enable_wal_mode(dbapi_conn, connection_record) -> None:
    """Enable WAL mode and set optimization pragmas for SQLite.

    This function should be registered as an event listener on SQLite engines.
    WAL mode enables concurrent reads and single writer, critical for multi-process access.
    """
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-64000")
    cursor.execute("PRAGMA temp_store=MEMORY")
    cursor.execute("PRAGMA mmap_size=30000000000")
    cursor.execute("PRAGMA wal_autocheckpoint=1000")
    cursor.execute("PRAGMA busy_timeout=10000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_db_engine(database_url: str, echo: bool = False):
    """Create SQLAlchemy engine with WAL mode for SQLite.

    Args:
        database_url: Database URL (SQLite or other)
        echo: Enable SQL query logging

    Returns:
        SQLAlchemy engine instance
    """
    engine = create_engine(database_url, connect_args={"check_same_thread": False}, echo=echo)

    # Register WAL mode listener for SQLite
    if "sqlite" in database_url.lower():
        event.listen(engine, "connect", enable_wal_mode)

    return engine


def create_session_factory(engine):
    """Create session factory from engine.

    Args:
        engine: SQLAlchemy engine

    Returns:
        Session factory
    """
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db_session(session_factory) -> Generator[Session, None, None]:
    """Database session dependency for FastAPI.

    Args:
        session_factory: SessionLocal factory

    Yields:
        Database session
    """
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


# Create engine with WAL mode
engine = create_db_engine(Config.STORE_DATABASE_URL, echo=False)
SessionLocal = create_session_factory(engine)


def get_db():
    """Get database session for FastAPI dependency injection."""
    yield from get_db_session(SessionLocal)
