
from ..common.utils import ensure_cl_server_dir
from ..common.config import BaseConfig, QdrantCollectionsConfig


class MInsightConfig(BaseConfig):
    """mInsight process configuration."""

    # Process identity
    id: str
    
    store_port: int = 8011
    
    # ML Service URLs (Worker only)
    auth_service_url: str = "http://localhost:8010"
    compute_service_url: str = "http://localhost:8012"
    compute_username: str = "admin"
    compute_password: str = "admin"
    
    # Worker processing settings
    face_vector_size: int = 512
    face_embedding_threshold: float = 0.7
    
    # MQTT configuration (Override default to add topic)
    mqtt_topic: str = "m_insight/wakeup"

    @classmethod
    def from_cli_args(cls, args) -> "MInsightConfig":
        """Create config from CLI arguments and environment."""
        cl_dir = ensure_cl_server_dir(create_if_missing=True)
        
        return cls(
            # BaseConfig fields
            cl_server_dir=cl_dir,
            media_storage_dir=cl_dir / "media",
            public_key_path=cl_dir / "keys" / "public_key.pem",
            auth_disabled=args.no_auth,
            qdrant_url=args.qdrant_url,
            qdrant_collections=QdrantCollectionsConfig(
                clip_embedding_collection_name=args.qdrant_collection,
                dino_embedding_collection_name=args.dino_collection,
                face_embedding_collection_name=args.face_collection,
            ),
            mqtt_broker=args.mqtt_broker,
            mqtt_port=args.mqtt_port,

            # MInsightConfig fields
            id=args.id,
            store_port=args.store_port,
            
            # ML Services
            auth_service_url=args.auth_url,
            compute_service_url=args.compute_url,
            compute_username=args.compute_username,
            compute_password=args.compute_password,
            
            mqtt_topic=args.mqtt_topic or f"store/{args.store_port}/items",
        )
