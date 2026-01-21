
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
    
    # Auth
    auth_disabled: bool
    server_port: int
    
    # MQTT configuration
    mqtt_broker: str
    mqtt_port: Optional[int] = None
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
            auth_disabled=False,
            server_port=args.store_port,
            mqtt_broker=args.mqtt_broker,
            mqtt_port=args.mqtt_port,
            mqtt_topic=args.mqtt_topic or f"store/{args.store_port}/items",
        )
