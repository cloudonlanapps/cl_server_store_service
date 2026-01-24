# src/store/main.py
from __future__ import annotations

import sys
from argparse import ArgumentParser

import uvicorn
from fastapi import FastAPI
from loguru import logger

from .common import utils
from .db_service.db_internals import (
    database,
    versioning,  # CRITICAL: Import versioning before database or models  # pyright: ignore[reportUnusedImport]  # noqa: F401
)
from .store.config import get_config
from .store.media_metadata import validate_tools
from .store.store import app




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

    # Create configuration
    config = get_config()

    # Validate required tools before starting server
    try:
        validate_tools()
        logger.info("Required tools validated: ExifTool and ffprobe are available")
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    # Start server (blocks)
    try:
        kwargs = {
            "host": config.host,
            "port": config.port,
            "log_level": config.log_level,
        }

        if config.reload:
            logger.info(f"Starting Store service with RELOAD on {config.host}:{config.port}")
            uvicorn.run("store.store:app", reload=True, **kwargs)
        else:
            logger.info(f"Starting Store service on {config.host}:{config.port}")
            uvicorn.run(app, **kwargs)

    except Exception as exc:
        print(f"Error starting service: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
