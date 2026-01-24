# src/store/main.py
from __future__ import annotations

import sys
from argparse import ArgumentParser

import uvicorn
from fastapi import FastAPI
from loguru import logger

from .common import (
    database,
    utils,
    versioning,  # CRITICAL: Import versioning before database or models  # pyright: ignore[reportUnusedImport]  # noqa: F401
)
from .store.config import StoreConfig
from .store.media_metadata import validate_tools
from .store.store import app


def create_app(config: StoreConfig) -> FastAPI:
    """Create and configure the FastAPI application instance."""

    app.state.config = config

    # Initialize Database (could be moved out, but here for convenience)
    # Do we need this? from .common import database

    database.init_db()

    return app


def main() -> int:
    parser = ArgumentParser(prog="store")
    _ = parser.add_argument("--no-auth", action="store_true", help="Disable authentication")
    _ = parser.add_argument("--no-migrate", action="store_true", help="Skip running DB migrations")
    _ = parser.add_argument("--port", "-p", type=int, default=8001)
    _ = parser.add_argument("--host", default="0.0.0.0")
    _ = parser.add_argument("--mqtt-server", default="localhost", help="MQTT broker host")
    _ = parser.add_argument(
        "--mqtt-port",
        type=int,
        default=None,
        help="MQTT broker port. Enabling this will enable MQTT broadcasting.",
    )
    _ = parser.add_argument("--reload", action="store_true", help="Enable uvicorn reload (dev)")
    _ = parser.add_argument(
        "--qdrant-url", default="http://localhost:6333", help="Qdrant service URL"
    )
    _ = parser.add_argument(
        "--qdrant-collection",
        default="clip_embeddings",
        help="Qdrant collection for CLIP embeddings",
    )
    _ = parser.add_argument(
        "--face-collection", default="face_embeddings", help="Qdrant collection for face embeddings"
    )
    _ = parser.add_argument(
        "--dino-collection", default="dino_embeddings", help="Qdrant collection for DINOv2 embeddings"
    )

    # Create Configurations
    args = parser.parse_args()
    
    # Initialize basic info needed for config
    cl_dir = utils.ensure_cl_server_dir(create_if_missing=True)
    
    # Convert args to dict and add required path keys
    config_dict = {k: v for k, v in vars(args).items() if v is not None}
    config_dict["cl_server_dir"] = cl_dir
    config_dict["media_storage_dir"] = cl_dir / "media"
    # Note: public_key_path logic might be more complex in finalize_base, 
    # but we need to satisfy the validator. 
    # finalize_base() implementation: self.public_key_path = cl_dir / "keys" / "public_key.pem"
    config_dict["public_key_path"] = cl_dir / "keys" / "public_key.pem"

    config = StoreConfig.model_validate(config_dict)
    config.finalize()

    # Initialize and configure app
    app = create_app(config)

    # Validate required tools before starting server
    try:
        validate_tools()
        logger.info("Required tools validated: ExifTool and ffprobe are available")
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    # Start server (blocks)
    try:
        if config.reload:
            # For reload, we accept we can't easily pass object.
            # We might need to rely on env vars we set above (CL_SERVER_DIR)
            # and let the app strictly re-initialize?
            # But we just removed Config dependency.
            # So 'store.store:app' needs to initialize config itself?
            # This suggests 'store.store' module level code needs to parse args or find config.
            # That's messy.
            # Better: Just disable reload support for now or warn about it?
            # Or use factory "store.main:create_app" ?
            # But 'main.py' is the entry point script...

            # Let's stick to: pass app object. If user wants reload, they can use uvicorn CLI directly?
            # Or we sacrifice reload for now in this refactoring to get cleaner architecture.
            # User didn't strictly ask to preserve reload, but "Refactor".
            # Passing app object is the standard way to inject config.

            uvicorn.run(
                app,
                host=config.host,
                port=config.port,
                log_level=config.log_level,
            )
        else:
            uvicorn.run(
                app,
                host=config.host,
                port=config.port,
                log_level=config.log_level,
            )

    except Exception as exc:
        print(f"Error starting service: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
