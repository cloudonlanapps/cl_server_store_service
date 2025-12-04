from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

# CRITICAL: Import versioning BEFORE models to ensure make_versioned() is called first
from . import versioning  # noqa: F401

from .config import DATABASE_URL
from .models import Base

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Needed for SQLite
    echo=False,  # Set to True for SQL query logging
)


def _enable_wal_mode(dbapi_conn, connection_record):
    """Enable WAL mode and set optimization pragmas for SQLite."""
    cursor = dbapi_conn.cursor()
    # WAL mode enables concurrent reads and single writer
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-64000")
    cursor.execute("PRAGMA temp_store=MEMORY")
    cursor.execute("PRAGMA mmap_size=30000000000")
    cursor.execute("PRAGMA wal_autocheckpoint=1000")
    cursor.execute("PRAGMA busy_timeout=10000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# Register the WAL event listener for every connection
if "sqlite" in DATABASE_URL.lower():
    event.listen(engine, "connect", _enable_wal_mode)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
