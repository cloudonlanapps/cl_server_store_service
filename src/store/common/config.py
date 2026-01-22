from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class BaseConfig(BaseModel, Namespace):
    """Base configuration shared between Store and MInsight, compliant with Namespace."""

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    def __init__(self, **kwargs):
        # Satisfy both BaseModel and Namespace
        BaseModel.__init__(self, **kwargs)
        Namespace.__init__(self)

    # Paths (populated after CLI parsing by finalize_base)
    cl_server_dir: Path | None = None
    media_storage_dir: Path | None = None
    public_key_path: Path | None = None

    # Auth
    no_auth: bool = False

    # Qdrant configuration
    qdrant_url: str = "http://localhost:6333"

    # Vector Store Collections
    qdrant_collection: str = "clip_embeddings"  # For CLIP
    dino_collection: str = "dino_embeddings"
    face_collection: str = "face_embeddings"

    # MQTT configuration
    mqtt_server: str = "localhost"
    mqtt_port: int | None = None

    def finalize_base(self):
        """Finalize base configuration after CLI parsing."""
        from .utils import ensure_cl_server_dir

        # Initialize Paths
        cl_dir = ensure_cl_server_dir(create_if_missing=True)
        self.cl_server_dir = cl_dir
        self.media_storage_dir = cl_dir / "media"
        self.public_key_path = cl_dir / "keys" / "public_key.pem"
