from cl_ml_tools import BroadcasterBase
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from store.db_service import DBService
from store.db_service.dependencies import get_db_service
from store.db_service.db_internals import get_db
from store.db_service.config import ConfigDBService
from store.vectorstore_services.vector_stores import (
    QdrantVectorStore,
    get_clip_store_dep,
    get_dino_store_dep,
    get_face_store_dep,
)

from .config import StoreConfig
from store.broadcast_service.monitor import MInsightMonitor
from .service import EntityService


def get_config(request: Request) -> StoreConfig:
    """Dependency to get StoreConfig from app state."""
    return request.app.state.config  # pyright: ignore[reportAny]


def get_config_service(db: DBService = Depends(get_db_service)) -> ConfigDBService:
    """Dependency to get ConfigDBService instance."""
    return db.config


def get_broadcaster(request: Request) -> BroadcasterBase | None:
    """Dependency to get broadcaster from app state."""
    return getattr(request.app.state, "broadcaster", None)  # pyright: ignore[reportAny]


def get_monitor(request: Request) -> MInsightMonitor | None:
    """Dependency to get monitor from app state."""
    return getattr(request.app.state, "monitor", None)  # pyright: ignore[reportAny]


def get_entity_service(
    db: Session = Depends(get_db),
    config: StoreConfig = Depends(get_config),
    db_service: DBService = Depends(get_db_service),
    clip_store: QdrantVectorStore = Depends(get_clip_store_dep),
    dino_store: QdrantVectorStore = Depends(get_dino_store_dep),
    face_store: QdrantVectorStore = Depends(get_face_store_dep),
    broadcaster: BroadcasterBase | None = Depends(get_broadcaster),
) -> EntityService:
    """Dependency to get EntityService instance.

    This creates a new service instance per request (because db is request-scoped).
    Injects deletion dependencies via FastAPI dependency injection.

    Note: FaceService is now MANDATORY. If Qdrant is unavailable, the dependency
    injection will fail early with a 500 error, which is acceptable since
    intelligence features require Qdrant to function.
    """
    # Create FaceService (face_store is now always available and required)
    from .face_service import FaceService
    from ..common.storage import StorageService

    # Create a DBService with the request's db session to avoid transaction conflicts
    db_service_with_session = DBService(db=db)

    storage_service = StorageService(base_dir=str(config.media_storage_dir))
    face_service = FaceService(
        db=db,
        db_service=db_service_with_session,
        face_store=face_store,
        storage_service=storage_service,
    )

    return EntityService(
        db,
        config,
        face_service=face_service,  # Now always present, not Optional
        clip_store=clip_store,
        dino_store=dino_store,
        broadcaster=broadcaster,
    )
