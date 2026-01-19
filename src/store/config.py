
from dataclasses import dataclass
from pathlib import Path
from .utils import ensure_cl_server_dir, get_db_url

from .pysdk_config import PySDKRuntimeConfig


@dataclass
class StoreConfig:
    """Store service configuration."""

    cl_server_dir: Path
    
    pysdk_config: PySDKRuntimeConfig
    media_storage_dir: Path
    public_key_path: Path
    auth_disabled: bool

    @classmethod
    def from_cli_args(cls, args) -> "StoreConfig":
        """Create config from CLI arguments and environment."""
        cl_dir =  ensure_cl_server_dir(create_if_missing=True)
        
        # Create PySDK configuration from CLI arguments
        pysdk_config = PySDKRuntimeConfig(
            auth_service_url=args.auth_url,
            compute_service_url=args.compute_url,
            compute_username=args.compute_username,
            compute_password=args.compute_password,
            qdrant_url=args.qdrant_url,
            qdrant_collection_name=args.qdrant_collection,
            face_store_collection_name=args.face_collection,
            face_embedding_threshold=args.face_threshold,
        )

        return cls(
            cl_server_dir=cl_dir,
            pysdk_config=pysdk_config,
            media_storage_dir=cl_dir / "media",
            public_key_path=cl_dir / "keys" / "public_key.pem",
            auth_disabled=args.no_auth,
        )
