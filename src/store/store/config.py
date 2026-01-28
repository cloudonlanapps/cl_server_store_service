from __future__ import annotations
import sys
from argparse import ArgumentParser
from typing import ClassVar

from ..common import utils
from ..common.config import BaseConfig


_config: StoreConfig | None = None


class StoreConfig(BaseConfig):
    """Unified Store service configuration and CLI arguments."""

    # CLI Fields (mapped from argparse)
    host: str = "0.0.0.0"
    port: int = 8001
    debug: bool = False
    reload: bool = False
    log_level: str = "info"
    no_migrate: bool = False

    def finalize(self):
        """Finalize configuration after CLI parsing."""
        self.finalize_base()


def get_config() -> StoreConfig:
    """Get or create the global StoreConfig singleton.

    If not already initialized, it parses sys.argv to create the config.
    """
    global _config
    if _config is not None:
        return _config

    parser = ArgumentParser(prog="store")
    parser.add_argument("--no-auth", action="store_true", help="Disable authentication")
    parser.add_argument("--no-migrate", action="store_true", help="Skip running DB migrations")
    parser.add_argument("--port", "-p", type=int, default=8001)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--mqtt-server", default="localhost", help="MQTT broker host")
    parser.add_argument(
        "--mqtt-port",
        type=int,
        default=None,
        help="MQTT broker port. Enabling this will enable MQTT broadcasting.",
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
    config_dict = {k: v for k, v in vars(args).items() if v is not None}
    config_dict["cl_server_dir"] = cl_dir
    config_dict["media_storage_dir"] = cl_dir / "media"
    config_dict["public_key_path"] = cl_dir / "keys" / "public_key.pem"

    _config = StoreConfig.model_validate(config_dict)
    _config.finalize()
    return _config
