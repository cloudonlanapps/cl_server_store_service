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
from store.broadcast_service.broadcaster import MInsightBroadcaster, get_insight_broadcaster
from store.broadcast_service.monitor import MInsightMonitor
from .service import EntityService


def get_config(request: Request) -> StoreConfig:
    """Dependency to get StoreConfig from app state."""
    return request.app.state.config  # pyright: ignore[reportAny]


def get_config_service(db: DBService = Depends(get_db_service)) -> ConfigDBService:
    """Dependency to get ConfigDBService instance."""
    return db.config


def get_broadcaster(request: Request) -> MInsightBroadcaster | None:
    """Dependency to get broadcaster.
    
    Preference 1: Existing broadcaster in app state (set by lifespan).
    Preference 2: Lazy initialize from config if not yet set (for tests or alternate entry points).
    """
    if hasattr(request.app.state, "broadcaster"):
        return request.app.state.broadcaster

    config = get_config(request)
    if not config.mqtt_url:
        return None

    bc = get_insight_broadcaster(config)
    # Sync back to app state to maintain lifecycle consistency
    request.app.state.broadcaster = bc
    return bc


def get_monitor(request: Request) -> MInsightMonitor | None:
    """Dependency to get monitor from app state."""
    return getattr(request.app.state, "monitor", None)  # pyright: ignore[reportAny]


def get_clip_store_dep(request: Request) -> QdrantVectorStore:
    """Dependency to get CLIP vector store, using app state config."""
    config = get_config(request)
    from store.vectorstore_services.vector_stores import get_clip_store
    return get_clip_store(
        url=config.qdrant_url,
        collection_name=config.qdrant_collection,
    )


def get_dino_store_dep(request: Request) -> QdrantVectorStore:
    """Dependency to get DINO vector store, using app state config."""
    config = get_config(request)
    from store.vectorstore_services.vector_stores import get_dino_store
    return get_dino_store(
        url=config.qdrant_url,
        collection_name=config.dino_collection,
    )


def get_face_store_dep(request: Request) -> QdrantVectorStore:
    """Dependency to get Face vector store, using app state config."""
    config = get_config(request)
    from store.vectorstore_services.vector_stores import get_face_store
    return get_face_store(
        url=config.qdrant_url,
        collection_name=config.face_collection,
        vector_size=getattr(config, "face_vector_size", 512),
    )


def get_entity_service(
    db: Session = Depends(get_db),
    config: StoreConfig = Depends(get_config),
    clip_store: QdrantVectorStore = Depends(get_clip_store_dep),
    dino_store: QdrantVectorStore = Depends(get_dino_store_dep),
    face_store: QdrantVectorStore = Depends(get_face_store_dep),
    broadcaster: MInsightBroadcaster | None = Depends(get_broadcaster),
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
    from store.db_service import DBService

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
