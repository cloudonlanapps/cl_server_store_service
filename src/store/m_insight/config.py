
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..common.utils import ensure_cl_server_dir


@dataclass
class MInsightConfig:
    """mInsight process configuration."""

    # Process identity
    id: str
    
    # Paths
    cl_server_dir: Path
    media_storage_dir: Path
    public_key_path: Path
    store_port: int = 8011
    
    # ML Service URLs (Worker only)
    auth_service_url: str = "http://localhost:8010"
    compute_service_url: str = "http://localhost:8012"
    compute_username: str = "admin"
    compute_password: str = "admin"
    
    # Worker processing settings
    face_vector_size: int = 512
    face_embedding_threshold: float = 0.7
    
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
            store_port=args.store_port,
            
            # ML Services
            auth_service_url=getattr(args, "auth_url", "http://localhost:8010"),
            compute_service_url=getattr(args, "compute_url", "http://localhost:8012"),
            compute_username=getattr(args, "compute_username", "admin"),
            compute_password=getattr(args, "compute_password", "admin"),
            
            mqtt_broker=args.mqtt_broker,
            mqtt_port=args.mqtt_port,
            mqtt_topic=args.mqtt_topic or f"store/{args.store_port}/items",
        )
