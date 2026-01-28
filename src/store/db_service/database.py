from __future__ import annotations

import time
from collections.abc import Callable, Generator
from typing import ParamSpec, TypeVar, cast

from loguru import logger
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from ..common.utils import get_db_url
# CRITICAL: Import versioning BEFORE models to ensure make_versioned() is called first
from . import versioning as _versioning  # noqa: F401  # pyright: ignore[reportUnusedImport]
# Global session factory
SessionLocal: sessionmaker[Session] = cast(sessionmaker[Session], cast(object, None))
engine: Engine = cast(Engine, cast(object, None))

T = TypeVar("T")
P = ParamSpec("P")


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
        is_memory = any(
            cast(str, row[2]) == "" for row in cast(list[tuple[object, object, object]], db_list)
        )

        if not is_memory:
            # Only set WAL mode for file-based databases
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA cache_size=-64000")
            cursor.execute("PRAGMA temp_store=MEMORY")
            cursor.execute("PRAGMA mmap_size=30000000000")
            cursor.execute("PRAGMA wal_autocheckpoint=1000")
            cursor.execute("PRAGMA busy_timeout=60000")

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
    kwargs: dict[str, object] = {
        "connect_args": {"check_same_thread": False},
        "echo": echo,
    }

    # SQLite-specific pooling logic
    if db_url.lower().startswith("sqlite"):
        # Check if this is an in-memory database
        # These URLs typically contain ':memory:' or are empty
        if ":memory:" in db_url or db_url.strip() == "sqlite://":
            # In-memory SQLite uses StaticPool by default,
            # which doesn't support pool_size or max_overflow
            pass
        else:
            # For file-based SQLite, we want a real pool to support high concurrency
            # especially for WAL mode and batch tests.

            kwargs.update(
                {
                    "poolclass": QueuePool,
                    "pool_size": 20,
                    "max_overflow": 40,
                }
            )
    else:
        # For other databases (Postgres, MySQL, etc.), use standard pooling
        kwargs.update(
            {
                "pool_size": 20,
                "max_overflow": 40,
            }
        )

    engine = create_engine(db_url, **kwargs)

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


def init_db() -> None:
    """Initialize database connection."""
def init_db() -> None:
    """Initialize database connection."""
    global SessionLocal, engine
    if SessionLocal is not None:
        return
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
        init_db()
    yield from get_db_session(SessionLocal)


def with_retry(
    max_retries: int = 5, initial_delay: float = 0.5
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator to retry a function on SQLite locking errors."""

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_error: OperationalError | None = None
            delay = initial_delay
            for i in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except OperationalError as e:
                    if "database is locked" in str(e).lower():
                        last_error = e
                        logger.warning(
                            f"Database locked, retrying {i + 1}/{max_retries} after {delay}s..."
                        )
                        time.sleep(delay)
                        delay *= 2  # Exponential backoff
                    else:
                        raise
            if last_error:
                raise last_error
            raise OperationalError(
                "Max retries exceeded", None, cast(Exception, cast(object, None))
            )

        return wrapper

    return decorator
