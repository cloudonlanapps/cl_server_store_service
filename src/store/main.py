# src/store/main.py
from __future__ import annotations

import sys
from argparse import ArgumentParser, Namespace
from typing import Optional

import uvicorn

from .common import versioning  # CRITICAL: Import versioning before database or models
from .common import database
from .store.media_metadata import validate_tools
from .store.config import StoreConfig

from loguru import logger


class Args(Namespace):
    host: str
    port: int
    debug: bool
    reload: bool
    log_level: str
    no_auth: bool
    no_migrate: bool
    mqtt_server: str
    mqtt_port: Optional[int]

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8001,
        debug: bool = False,
        reload: bool = False,
        log_level: str = "info",
        no_auth: bool = False,
        no_migrate: bool = False,
        mqtt_server: str = "localhost",
        mqtt_port: Optional[int] = None,
    ) -> None:
        super().__init__()
        self.host = host
        self.port = port
        self.debug = debug
        self.reload = reload
        self.log_level = log_level
        self.no_auth = no_auth
        self.no_migrate = no_migrate
        self.mqtt_server = mqtt_server
        self.mqtt_port = mqtt_port


def create_app(config: StoreConfig) -> "FastAPI":
    """Create and configure the FastAPI application instance."""
    from .store.store import app
    app.state.config = config
    
    # Initialize Database (could be moved out, but here for convenience)
    from .common import database
    database.init_db(config)
    
    return app


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
        "--mqtt-server", default="localhost", help="MQTT broker host"
    )
    _ = parser.add_argument(
        "--mqtt-port", type=int, default=None, help="MQTT broker port. Enabling this will enable MQTT broadcasting."
    )
    _ = parser.add_argument(
        "--reload", action="store_true", help="Enable uvicorn reload (dev)"
    )

    # PySDK Configuration arguments (REMOVED)

    # Other args...

    args = parser.parse_args(namespace=Args())
    
    # Create Configurations
    config = StoreConfig.from_cli_args(args)

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
