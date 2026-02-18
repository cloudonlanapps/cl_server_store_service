from __future__ import annotations
from argparse import ArgumentParser
from pathlib import Path
from typing import ClassVar

from ..common import utils
from ..common.config import BaseConfig



class StoreConfig(BaseConfig):
    """Unified Store service configuration and CLI arguments."""

    _instance: ClassVar[StoreConfig | None] = None

    # CLI Fields (mapped from argparse)
    host: str
    port: int
    debug: bool
    reload: bool
    log_level: str
    no_migrate: bool
    
    # Compute Service (for HLS generation)
    compute_url: str | None = None
    compute_username: str | None = None
    compute_password: str | None = None
    auth_url: str | None = None

    # Calculated Fields
    cl_server_dir: Path
    media_storage_dir: Path
    stream_storage_dir: Path
    public_key_path: Path

    @classmethod
    def get_config(cls) -> StoreConfig:
        """Get or create the unified StoreConfig singleton."""
        if cls._instance is None:
            cls._instance = cls._from_cli_args()
        return cls._instance

    @classmethod
    def _from_cli_args(cls) -> StoreConfig:
        """Parse CLI arguments and return a StoreConfig instance."""
        parser = ArgumentParser(prog="store")
        parser.add_argument("--no-auth", action="store_true", help="Disable authentication")
        parser.add_argument("--no-migrate", action="store_true", help="Skip running DB migrations")
        parser.add_argument("--port", "-p", type=int, default=8001)
        parser.add_argument("--host", default="0.0.0.0")
        parser.add_argument(
            "--mqtt-url",
            default="mqtt://localhost:1883",
            help="MQTT broker URL (e.g. mqtt://localhost:1883)",
        )
        parser.add_argument("--reload", action="store_true", help="Enable uvicorn reload (dev)")
        parser.add_argument(
            "--qdrant-url", default="http://localhost:6333", help="Qdrant service URL"
        )
        parser.add_argument(
            "--qdrant-collection",
            default="clip_embeddings",
            help="Qdrant collection for CLIP embeddings",
        )
        parser.add_argument(
            "--face-collection", default="face_embeddings", help="Qdrant collection for face embeddings"
        )
        parser.add_argument(
            "--dino-collection", default="dino_embeddings", help="Qdrant collection for DINOv2 embeddings"
        )
        
        # Compute connectivity
        parser.add_argument("--auth-url", default="http://localhost:8010", help="Auth service URL")
        parser.add_argument("--compute-url", default="http://localhost:8012", help="Compute service URL")
        parser.add_argument("--compute-username", default="admin", help="Compute service username")
        parser.add_argument("--compute-password", default="admin", help="Compute service password")
        
        parser.add_argument("--debug", action="store_true", help="Enable debug mode")
        parser.add_argument(
            "--log-level",
            default="info",
            choices=["critical", "error", "warning", "info", "debug", "trace"],
        )

        # Parse arguments - ignoring unknown args to be safe when running under reloaders/tests
        args, _ = parser.parse_known_args()

        # Initialize basic info needed for config
        try:
            cl_dir = utils.ensure_cl_server_dir(create_if_missing=True)
        except SystemExit:
            # If running in a context where CL_SERVER_DIR can't be set yet (like some test setups),
            # use a temporary or dummy path if needed?
            # For now, let it fail as it's a critical requirement.
            raise

        # Convert args to dict and add required path keys
        config_dict = vars(args).copy()
        config_dict["cl_server_dir"] = cl_dir
        config_dict["media_storage_dir"] = cl_dir / "media"
        config_dict["stream_storage_dir"] = cl_dir / "media" / "streams"
        config_dict["public_key_path"] = cl_dir / "keys" / "public_key.pem"
        
        # Ensure no_auth is present even if not in args (though it should be from store_true)
        if "no_auth" not in config_dict:
            config_dict["no_auth"] = False

        config = cls.model_validate(config_dict)
        return config
