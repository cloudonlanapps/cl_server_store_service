
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..common.utils import ensure_cl_server_dir


@dataclass
class StoreConfig:
    """Store service configuration."""

    cl_server_dir: Path
    
    media_storage_dir: Path
    public_key_path: Path
    auth_disabled: bool
    
    server_port: int
    mqtt_broker: str = "localhost"
    mqtt_port: Optional[int] = None
    
    # Qdrant configuration (required for Store REST API Search)
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_name: str = "image_embeddings"
    face_store_collection_name: str = "face_embeddings"



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
            mqtt_broker=getattr(args, "mqtt_server", "localhost"),
            mqtt_port=getattr(args, "mqtt_port", None),
            qdrant_url=getattr(args, "qdrant_url", "http://localhost:6333"),
            qdrant_collection_name=getattr(args, "qdrant_collection", "image_embeddings"),
            face_store_collection_name=getattr(args, "face_collection", "face_embeddings"),
        )
