from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class BaseConfig(BaseModel):
    """Base configuration shared between Store and MInsight, compliant with Namespace."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        arbitrary_types_allowed=True, validate_assignment=True
    )

    # Paths (populated after CLI parsing)
    cl_server_dir: Path
    media_storage_dir: Path
    public_key_path: Path

    # Auth
    no_auth: bool

    # Qdrant configuration
    qdrant_url: str

    # Vector Store Collections
    qdrant_collection: str
    dino_collection: str
    face_collection: str

    # MQTT configuration
    mqtt_url: str


