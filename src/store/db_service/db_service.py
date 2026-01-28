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

    def __init__(self, db=None):
        """Initialize all table services.
        
        Args:
            db: Optional DB session to share across services (for testing/transactions)
        """
        from . import database
        if database.SessionLocal is None:
            database.init_db()

        self.entity = EntityDBService(db=db)
        self.entity_version = EntityVersionDBService(db=db)
        self.face = FaceDBService(db=db)
        self.known_person = KnownPersonDBService(db=db)
        self.sync_state = EntitySyncStateDBService(db=db)
        self.config = ConfigDBService(db=db)
