from cl_ml_tools import BroadcasterBase
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from store.db_service import DBService
from store.db_service.dependencies import get_db_service
from store.db_service.db_internals import get_db
from store.db_service.config import ConfigDBService

from .config import StoreConfig
from store.broadcast_service.monitor import MInsightMonitor
from .service import EntityService


def get_config(request: Request) -> StoreConfig:
    """Dependency to get StoreConfig from app state."""
    return request.app.state.config  # pyright: ignore[reportAny]


def get_config_service(db: DBService = Depends(get_db_service)) -> ConfigDBService:
    """Dependency to get ConfigDBService instance."""
    return db.config


def get_entity_service(
    request: Request,
    db: Session = Depends(get_db),
    config: StoreConfig = Depends(get_config),
    db_service: DBService = Depends(get_db_service),
) -> EntityService:
    """Dependency to get EntityService instance.

    This creates a new service instance per request (because db is request-scoped).
    Injects deletion dependencies from app state.
    """
    # Get deletion dependencies from app state
    clip_store = getattr(request.app.state, "clip_store", None)
    dino_store = getattr(request.app.state, "dino_store", None)
    face_store = getattr(request.app.state, "face_store", None)
    broadcaster = getattr(request.app.state, "broadcaster", None)

    # Create FaceService if face_store is available
    face_service = None
    if face_store:
        from .face_service import FaceService
        from ..common.storage import StorageService

        storage_service = StorageService(base_dir=str(config.media_storage_dir))
        face_service = FaceService(
            db=db,
            db_service=db_service,
            face_store=face_store,
            storage_service=storage_service,
        )

    return EntityService(
        db,
        config,
        face_service=face_service,
        clip_store=clip_store,
        dino_store=dino_store,
        broadcaster=broadcaster,
    )


def get_broadcaster(request: Request) -> BroadcasterBase | None:
    """Dependency to get broadcaster from app state."""
    return getattr(request.app.state, "broadcaster", None)  # pyright: ignore[reportAny]


def get_monitor(request: Request) -> MInsightMonitor | None:
    """Dependency to get monitor from app state."""
    return getattr(request.app.state, "monitor", None)  # pyright: ignore[reportAny]
