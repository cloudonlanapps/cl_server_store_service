
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..common.utils import ensure_cl_server_dir
from ..common.schemas import QdrantCollectionsConfig


@dataclass
class MInsightConfig:
    """mInsight process configuration."""

    # Process identity
    id: str
    
    # Paths
    cl_server_dir: Path
    media_storage_dir: Path
    public_key_path: Path
    auth_disabled: bool = False
    store_port: int = 8011
    
    # ML Service URLs (Worker only)
    auth_service_url: str = "http://localhost:8010"
    compute_service_url: str = "http://localhost:8012"
    compute_username: str = "admin"
    compute_password: str = "admin"
    
    # Worker processing settings
    face_vector_size: int = 512
    face_embedding_threshold: float = 0.7
    
    # Qdrant configuration
    qdrant_url: str = "http://localhost:6333"
    qdrant_collections: QdrantCollectionsConfig = field(default_factory=QdrantCollectionsConfig)
    
    # MQTT configuration
    mqtt_broker: str = "localhost"
    mqtt_port: int = 1883
    mqtt_topic: str = "m_insight/wakeup"

    @classmethod
    def from_cli_args(cls, args) -> "MInsightConfig":
        """Create config from CLI arguments and environment."""
        cl_dir = ensure_cl_server_dir(create_if_missing=True)
        
        return cls(
            id=args.id,
            cl_server_dir=cl_dir,
            media_storage_dir=cl_dir / "media",
            public_key_path=cl_dir / "keys" / "public_key.pem",
            auth_disabled=args.no_auth,
            store_port=args.store_port,
            
            # ML Services
            auth_service_url=args.auth_url,
            compute_service_url=args.compute_url,
            compute_username=args.compute_username,
            compute_password=args.compute_password,
            
            # Qdrant
            qdrant_url=args.qdrant_url,
            qdrant_collections=QdrantCollectionsConfig(
                clip_embedding_collection_name=args.qdrant_collection,
                dino_embedding_collection_name=args.dino_collection,
                face_embedding_collection_name=args.face_collection,
            ),

            mqtt_broker=args.mqtt_broker,
            mqtt_port=args.mqtt_port,
            mqtt_topic=args.mqtt_topic or f"store/{args.store_port}/items",
        )
