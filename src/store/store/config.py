
from ..common.utils import ensure_cl_server_dir
from ..common.config import BaseConfig, QdrantCollectionsConfig


class StoreConfig(BaseConfig):
    """Store service configuration."""
    
    server_port: int = 8011


    @classmethod
    def from_cli_args(cls, args) -> "StoreConfig":
        """Create config from CLI arguments and environment."""
        cl_dir =  ensure_cl_server_dir(create_if_missing=True)
        
        return cls(
            cl_server_dir=cl_dir,
            media_storage_dir=cl_dir / "media",
            public_key_path=cl_dir / "keys" / "public_key.pem",
            auth_disabled=args.no_auth,
            qdrant_url=args.qdrant_url,
            qdrant_collections=QdrantCollectionsConfig(
                clip_embedding_collection_name=args.qdrant_collection,
                face_embedding_collection_name=args.face_collection,
            ),
            mqtt_broker=args.mqtt_server,
            mqtt_port=args.mqtt_port,
            
            server_port=args.port,
        )
