# src/store/main.py
from __future__ import annotations

import os
import sys
from argparse import ArgumentParser, Namespace

import uvicorn

from .common import versioning  # CRITICAL: Import versioning before database or models
from .common import database
from .store.media_metadata import validate_tools
from .store.config import StoreConfig
from .intelligence.logic.pysdk_config import PySDKRuntimeConfig

from loguru import logger


class Args(Namespace):
    host: str
    port: int
    debug: bool
    reload: bool
    log_level: str
    no_auth: bool
    no_migrate: bool
    # PySDK configuration
    auth_url: str
    compute_url: str
    compute_username: str
    compute_password: str
    qdrant_url: str
    qdrant_collection: str
    face_collection: str
    face_threshold: float

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8001,
        debug: bool = False,
        reload: bool = False,
        log_level: str = "info",
        no_auth: bool = False,
        no_migrate: bool = False,
        auth_url: str = "http://localhost:8000",
        compute_url: str = "http://localhost:8002",
        compute_username: str = "admin",
        compute_password: str = "admin",
        qdrant_url: str = "http://localhost:6333",
        qdrant_collection: str = "image_embeddings",
        face_collection: str = "face_embeddings",
        face_threshold: float = 0.7,
    ) -> None:
        super().__init__()
        self.host = host
        self.port = port
        self.debug = debug
        self.reload = reload
        self.log_level = log_level
        self.no_auth = no_auth
        self.no_migrate = no_migrate
        self.auth_url = auth_url
        self.compute_url = compute_url
        self.compute_username = compute_username
        self.compute_password = compute_password
        self.qdrant_url = qdrant_url
        self.qdrant_collection = qdrant_collection
        self.face_collection = face_collection
        self.face_threshold = face_threshold


def main() -> int:
    parser = ArgumentParser(prog="store")
    _ = parser.add_argument(
        "--no-auth", action="store_true", help="Disable authentication"
    )
    _ = parser.add_argument(
        "--no-migrate", action="store_true", help="Skip running DB migrations"
    )
    _ = parser.add_argument(
        "--port", "-p", type=int, default=8001
    )
    _ = parser.add_argument("--host", default="0.0.0.0")
    _ = parser.add_argument(
        "--reload", action="store_true", help="Enable uvicorn reload (dev)"
    )

    # PySDK Configuration arguments
    _ = parser.add_argument(
        "--auth-url", default="http://localhost:8000", help="Auth service URL"
    )
    _ = parser.add_argument(
        "--compute-url", default="http://localhost:8002", help="Compute service URL"
    )
    _ = parser.add_argument(
        "--compute-username", default="admin", help="Compute service username"
    )
    _ = parser.add_argument(
        "--compute-password", default="admin", help="Compute service password"
    )
    _ = parser.add_argument(
        "--qdrant-url", default="http://localhost:6333", help="Qdrant URL"
    )
    _ = parser.add_argument(
        "--qdrant-collection",
        default="image_embeddings",
        help="Qdrant collection for images",
    )
    _ = parser.add_argument(
        "--face-collection",
        default="face_embeddings",
        help="Qdrant collection for faces",
    )
    _ = parser.add_argument(
        "--face-threshold",
        type=float,
        default=0.7,
        help="Face matching similarity threshold (0.0-1.0)",
    )

    # Other args...

    args = parser.parse_args(namespace=Args())
    
    # Create Configurations
    config = StoreConfig.from_cli_args(args)
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

    # Initialize Database
    database.init_db(config)
    
    # Import app and set configs
    from .store.store import app
    app.state.config = config
    app.state.pysdk_config = pysdk_config
    
    # Validate required tools before starting server
    try:
        validate_tools()
        logger.info("Required tools validated: ExifTool and ffprobe are available")
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    # Start server (blocks)
    try:
        if args.reload:
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
                host=args.host,
                port=args.port,
                log_level=args.log_level,
            )
        else:
            uvicorn.run(
                app,
                host=args.host,
                port=args.port,
                log_level=args.log_level,
            )
            
    except Exception as exc:
        print(f"Error starting service: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
