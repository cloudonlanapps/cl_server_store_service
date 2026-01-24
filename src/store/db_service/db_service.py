from __future__ import annotations

from typing import TYPE_CHECKING
from .entity import EntityDBService, EntityVersionDBService
from .face import FaceDBService, KnownPersonDBService
from .intelligence import EntityJobDBService, ImageIntelligenceDBService
from .sync import EntitySyncStateDBService

if TYPE_CHECKING:
    from ..common.config import BaseConfig

class DBService:
    """Facade providing access to all table services.

    Each service manages its own sessions internally for multi-process safety.
    """

    def __init__(self):
        """Initialize all table services."""
        self.entity = EntityDBService()
        self.entity_version = EntityVersionDBService()
        self.intelligence = ImageIntelligenceDBService()
        self.job = EntityJobDBService()
        self.face = FaceDBService()
        self.known_person = KnownPersonDBService()
        self.sync_state = EntitySyncStateDBService()
