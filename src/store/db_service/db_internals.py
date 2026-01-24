from __future__ import annotations  # noqa: I001

# CRITICAL: Import versioning BEFORE models and database to ensure make_versioned() is called first
from . import versioning as _versioning  # noqa: F401  # pyright: ignore[reportUnusedImport]

from sqlalchemy_continuum import (
    version_class,  # pyright: ignore[reportAttributeAccessIssue, reportUnknownVariableType]
)

from . import database, models, versioning
from .database import (
    SessionLocal,
    create_db_engine,
    create_session_factory,
    enable_wal_mode,
    engine,
    get_db,
    get_db_session,
    init_db,
    with_retry,
)
from .models import (
    Base,
    Entity,
    EntityJob,
    EntitySyncState,
    Face,
    ImageIntelligence,
    KnownPerson,
    ServiceConfig,
)
from .versioning import (
    make_versioned,  # pyright: ignore[reportPrivateLocalImportUsage]
)


__all__ = [
    "database",
    "models",
    "versioning",
    "version_class",
    # Re-exporting database symbols
    "SessionLocal",
    "engine",
    "init_db",
    "get_db",
    "get_db_session",
    "create_db_engine",
    "create_session_factory",
    "enable_wal_mode",
    "with_retry",
    # Re-exporting models symbols
    "Base",
    "Entity",
    "EntityJob",
    "EntitySyncState",
    "Face",
    "ImageIntelligence",
    "KnownPerson",
    "ServiceConfig",
    "make_versioned",
]
