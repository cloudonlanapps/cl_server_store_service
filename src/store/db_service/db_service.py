from __future__ import annotations

from typing import TYPE_CHECKING
from .entity import EntityDBService, EntityVersionDBService
from .face import FaceDBService, FaceMatchDBService, KnownPersonDBService
from .intelligence import EntityJobDBService, ImageIntelligenceDBService
from .sync import EntitySyncStateDBService

if TYPE_CHECKING:
    from ..common.config import BaseConfig

class DBService:
    """Facade providing access to all table services.

    Each service manages its own sessions internally for multi-process safety.
    """

    def __init__(self, config: BaseConfig):
        """Initialize all table services.

        Args:
            config: Store configuration (no session stored)
        """
        self.entity = EntityDBService(config)
        self.entity_version = EntityVersionDBService(config)
        self.intelligence = ImageIntelligenceDBService(config)
        self.job = EntityJobDBService(config)
        self.face = FaceDBService(config)
        self.known_person = KnownPersonDBService(config)
        self.face_match = FaceMatchDBService(config)
        self.sync_state = EntitySyncStateDBService(config)
