from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class BaseConfig(BaseModel):
    """Base configuration shared between Store and MInsight, compliant with Namespace."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        arbitrary_types_allowed=True, validate_assignment=True
    )

    # Paths (populated after CLI parsing by finalize_base)
    cl_server_dir: Path
    media_storage_dir: Path
    public_key_path: Path

    # Auth
    no_auth: bool = False

    # Qdrant configuration
    qdrant_url: str = "http://localhost:6333"

    # Vector Store Collections
    qdrant_collection: str = "clip_embeddings"  # For CLIP
    dino_collection: str = "dino_embeddings"
    face_collection: str = "face_embeddings"

    # MQTT configuration
    mqtt_broker: str = "localhost"
    mqtt_port: int | None = None

    def finalize_base(self):
        """Finalize base configuration after CLI parsing."""
        from .utils import ensure_cl_server_dir

        # Initialize Paths
        cl_dir = ensure_cl_server_dir(create_if_missing=True)
        self.cl_server_dir = cl_dir
        self.media_storage_dir = cl_dir / "media"
        self.public_key_path = cl_dir / "keys" / "public_key.pem"
