from cl_ml_tools import BroadcasterBase
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from store.db_service import DBService
from store.db_service.dependencies import get_db_service
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
    db: Session = Depends(get_db),
    config: StoreConfig = Depends(get_config),
) -> EntityService:
    """Dependency to get EntityService instance.

    This creates a new service instance per request (because db is request-scoped).
    """
    return EntityService(db, config)


def get_broadcaster(request: Request) -> BroadcasterBase | None:
    """Dependency to get broadcaster from app state."""
    return getattr(request.app.state, "broadcaster", None)  # pyright: ignore[reportAny]


def get_monitor(request: Request) -> MInsightMonitor | None:
    """Dependency to get monitor from app state."""
    return getattr(request.app.state, "monitor", None)  # pyright: ignore[reportAny]
