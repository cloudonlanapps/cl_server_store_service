from cl_ml_tools import BroadcasterBase
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from store.common.database import get_db

from .config import StoreConfig
from .config_service import ConfigService
from .monitor import MInsightMonitor
from .service import EntityService


def get_config(request: Request) -> StoreConfig:
    """Dependency to get StoreConfig from app state."""
    return request.app.state.config  # pyright: ignore[reportAny]


def get_config_service(db: Session = Depends(get_db)) -> ConfigService:
    """Dependency to get ConfigService instance."""
    return ConfigService(db)


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
