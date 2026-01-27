from __future__ import annotations

from typing import TYPE_CHECKING
from .entity import EntityDBService, EntityVersionDBService
from .face import FaceDBService, KnownPersonDBService
from .sync import EntitySyncStateDBService
from .config import ConfigDBService

if TYPE_CHECKING:
    from ..common.config import BaseConfig

class DBService:
    """Facade providing access to all table services.

    Each service manages its own sessions internally for multi-process safety.
    """

    def __init__(self):
        """Initialize all table services."""
        from . import database
        if database.SessionLocal is None:
            database.init_db()

        self.entity = EntityDBService()
        self.entity_version = EntityVersionDBService()
        self.face = FaceDBService()
        self.known_person = KnownPersonDBService()
        self.sync_state = EntitySyncStateDBService()
        self.config = ConfigDBService()
