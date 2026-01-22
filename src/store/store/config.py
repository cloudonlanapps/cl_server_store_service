
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..common.utils import ensure_cl_server_dir
from ..common.schemas import QdrantCollectionsConfig


@dataclass
class StoreConfig:
    """Store service configuration."""

    cl_server_dir: Path
    
    media_storage_dir: Path
    public_key_path: Path
    auth_disabled: bool
    
    server_port: int = 8011
    mqtt_broker: str = "localhost"
    mqtt_port: Optional[int] = None
    
    # Qdrant configuration (required for Store REST API Search)
    qdrant_url: str = "http://localhost:6333"
    qdrant_collections: QdrantCollectionsConfig = field(default_factory=QdrantCollectionsConfig)



    @classmethod
    def from_cli_args(cls, args) -> "StoreConfig":
        """Create config from CLI arguments and environment."""
        cl_dir =  ensure_cl_server_dir(create_if_missing=True)
        
        return cls(
            cl_server_dir=cl_dir,
            media_storage_dir=cl_dir / "media",
            public_key_path=cl_dir / "keys" / "public_key.pem",
            auth_disabled=args.no_auth,
            server_port=args.port,
            mqtt_broker=args.mqtt_server,
            mqtt_port=args.mqtt_port,
            qdrant_url=args.qdrant_url,
            qdrant_collections=QdrantCollectionsConfig(
                clip_embedding_collection_name=args.qdrant_collection,
                face_embedding_collection_name=args.face_collection,
            ),
        )
