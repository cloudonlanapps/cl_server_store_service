from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .utils import ensure_cl_server_dir


class QdrantCollectionsConfig(BaseModel):
    """Configuration for Qdrant collection names."""

    clip_embedding_collection_name: str = Field(
        default="clip_embeddings", description="Collection name for CLIP embeddings"
    )
    dino_embedding_collection_name: str = Field(
        default="dino_embeddings", description="Collection name for DINOv2 embeddings"
    )
    face_embedding_collection_name: str = Field(
        default="face_embeddings", description="Collection name for face embeddings"
    )


class BaseConfig(BaseModel):
    """Base configuration shared between Store and MInsight."""

    # Paths
    cl_server_dir: Path
    media_storage_dir: Path
    public_key_path: Path
    
    # Auth
    auth_disabled: bool = False
    
    # Qdrant configuration
    qdrant_url: str = "http://localhost:6333"
    qdrant_collections: QdrantCollectionsConfig = Field(default_factory=QdrantCollectionsConfig)
    
    # MQTT configuration
    mqtt_broker: str = "localhost"
    mqtt_port: Optional[int] = None
