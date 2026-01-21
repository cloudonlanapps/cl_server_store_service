
from __future__ import annotations
from typing import TYPE_CHECKING
from collections.abc import Callable, Generator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.orm import Session, sessionmaker

# CRITICAL: Import versioning BEFORE models to ensure make_versioned() is called first
# Using absolute import to avoid circular dependency with __init__.py
from . import versioning  # pyright: ignore[reportUnusedImport]  # noqa: F401
from .utils import get_db_url

if TYPE_CHECKING:
    from ..store.config import StoreConfig

# Global session factory
SessionLocal: sessionmaker[Session] | None = None
engine: Engine | None = None


def enable_wal_mode(
    dbapi_conn: DBAPIConnection,
    connection_record: object,
) -> None:
    """Enable WAL mode and set optimization pragmas for SQLite.

    This function should be registered as an event listener on SQLite engines.
    WAL mode enables concurrent reads and single writer, critical for multi-process access.
    
    Note: WAL mode is skipped for in-memory databases as they don't support it,
    but foreign keys are still enabled for all SQLite databases.
    """
    _ = connection_record
    cursor = dbapi_conn.cursor()
    try:
        # Check if this is an in-memory database
        # In-memory databases have an empty string as the file path
        cursor.execute("PRAGMA database_list")
        db_list = cursor.fetchall()
        # db_list format: [(seq, name, file), ...]
        # For in-memory: file is '' (empty string)
        is_memory = any(row[2] == '' for row in db_list)
        
        if not is_memory:
            # Only set WAL mode for file-based databases
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA cache_size=-64000")
            cursor.execute("PRAGMA temp_store=MEMORY")
            cursor.execute("PRAGMA mmap_size=30000000000")
            cursor.execute("PRAGMA wal_autocheckpoint=1000")
            cursor.execute("PRAGMA busy_timeout=10000")
        
        # Always enable foreign keys for all SQLite databases (memory or file-based)
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def create_db_engine(
    db_url: str,
    *,
    echo: bool = False,
) -> Engine:
    """Create SQLAlchemy engine with WAL mode for SQLite.

    Args:
        db_url: Database URL (SQLite or other)
        echo: Enable SQL query logging

    Returns:
        SQLAlchemy engine instance
    """
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        echo=echo,
        pool_size=20,
        max_overflow=40,
    )

    # Register WAL mode listener for SQLite
    if db_url.lower().startswith("sqlite"):
        event.listen(engine, "connect", enable_wal_mode)

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create session factory from engine.

    Args:
        engine: SQLAlchemy engine

    Returns:
        Session factory
    """
    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        class_=Session,
    )


def init_db(config: StoreConfig) -> None:
    """Initialize database connection."""
    global SessionLocal, engine
    engine = create_db_engine(get_db_url(), echo=False)
    SessionLocal = create_session_factory(engine)


def get_db_session(
    session_factory: Callable[[], Session],
) -> Generator[Session, None, None]:
    """Database session dependency for FastAPI.

    Args:
        session_factory: Session factory callable

    Yields:
        Database session
    """
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def get_db() -> Generator[Session, None, None]:
    """Get database session for FastAPI dependency injection."""
    if SessionLocal is None:
        raise RuntimeError("Database not initialized")
    yield from get_db_session(SessionLocal)
