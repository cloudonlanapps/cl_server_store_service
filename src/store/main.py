# src/store/main.py
from __future__ import annotations

import sys
import uvicorn
from loguru import logger

from .db_service.db_internals import (
    versioning,  # CRITICAL: Import versioning before database or models  # pyright: ignore[reportUnusedImport]  # noqa: F401
)
from .store.config import StoreConfig
from .store.media_metadata import validate_tools
from .store.store import app




def main() -> int:
    # Create configuration
    config = StoreConfig.get_config()

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
            logger.info(f"Starting Store service with RELOAD on {config.host}:{config.port}")
            uvicorn.run(
                "store.store:app",  # Pass app as string for reload to work correctly
                host=config.host,
                port=config.port,
                log_level=config.log_level,
                reload=True,
            )
        else:
            logger.info(f"Starting Store service on {config.host}:{config.port}")
            uvicorn.run(
                app,  # Pass app object directly when not reloading
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
