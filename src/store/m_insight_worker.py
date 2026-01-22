#!/usr/bin/env python3
"""CLI entry point for m_insight process.

This module handles:
- CLI argument parsing
- Configuration setup
- Database initialization
- Signal handling for graceful shutdown
- MQTT listener setup
- Main run loop that calls mInsight.run_once()
"""

from __future__ import annotations

import asyncio
import signal
import sys
from argparse import ArgumentParser, Namespace
from types import FrameType

from loguru import logger

# Global shutdown event and signal counter
shutdown_event = asyncio.Event()
reconciliation_trigger = asyncio.Event()
shutdown_signal_count = 0


from .m_insight.broadcaster import MInsightBroadcaster


def signal_handler(signum: int, _frame: FrameType | None) -> None:
    """Handle shutdown signals (SIGINT, SIGTERM).
    
    First signal: Initiates graceful shutdown
    Second signal: Forces immediate exit
    """
    global shutdown_signal_count
    shutdown_signal_count += 1

    if shutdown_signal_count == 1:
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        logger.info("Press Ctrl+C again to force immediate exit")
        shutdown_event.set()
    else:
        # Use print to ensure message appears before exit
        print(
            "\nWARNING: Force exit requested, terminating immediately!",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)


class Args(Namespace):
    """CLI arguments for m_insight worker."""
    
    id: str
    log_level: str
    mqtt_broker: str
    mqtt_port: int | None
    mqtt_topic: str
    store_port: int
    auth_url: str
    compute_url: str
    compute_username: str
    compute_password: str
    qdrant_url: str
    qdrant_collection: str
    dino_collection: str
    face_collection: str
    no_auth: bool

    def __init__(
        self,
        id: str = "m-insight-default",
        log_level: str = "INFO",
        mqtt_broker: str = "localhost",
        mqtt_port: int = 1883,
        mqtt_topic: str | None = None,
        store_port: int = 8001,
        auth_url: str = "http://localhost:8010",
        compute_url: str = "http://localhost:8012",
        compute_username: str = "admin",
        compute_password: str = "admin",
        qdrant_url: str = "http://localhost:6333",
        qdrant_collection: str = "image_embeddings",
        dino_collection: str = "dino_embeddings",
        face_collection: str = "face_embeddings",
        no_auth: bool = False,
    ) -> None:
        super().__init__()
        self.id = id
        self.log_level = log_level
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.mqtt_topic = mqtt_topic
        self.store_port = store_port
        self.auth_url = auth_url
        self.compute_url = compute_url
        self.compute_username = compute_username
        self.compute_password = compute_password
        self.qdrant_url = qdrant_url
        self.qdrant_collection = qdrant_collection
        self.dino_collection = dino_collection
        self.face_collection = face_collection
        self.no_auth = no_auth



async def heartbeat_task(broadcaster: MInsightBroadcaster):
    """Periodic heartbeat task."""
    try:
        while not shutdown_event.is_set():
            broadcaster.publish_status("running")
            await asyncio.sleep(5) # 5 second heartbeat
    except asyncio.CancelledError:
        pass


async def mqtt_listener_task(config, processor) -> None:
    """Background task to listen for MQTT wake-up signals.
    
    Args:
        config: MInsightConfig instance
        processor: mInsight instance
    """
    if not config.mqtt_port:
        logger.info("MQTT disabled, skipping listener")
        return
    
    try:
        from cl_ml_tools import get_broadcaster
        
        broadcaster = get_broadcaster(
            broadcast_type="mqtt",
            broker=config.mqtt_broker,
            port=config.mqtt_port,
        )
        
        # Subscribe to wake-up topic
        def on_message(_client: object, _userdata: object, _message: object) -> None:
            """MQTT message callback - trigger reconciliation."""
            logger.debug(f"Received MQTT wake-up on {config.mqtt_topic}")
            # Signal the main loop to run reconciliation
            reconciliation_trigger.set()
        
        # Type ignore: broadcaster.client is dynamically typed from cl_ml_tools
        _ = broadcaster.client.subscribe(config.mqtt_topic)  # pyright: ignore[reportOptionalMemberAccess, reportAttributeAccessIssue, reportUnknownMemberType]
        broadcaster.client.on_message = on_message  # pyright: ignore[reportOptionalMemberAccess, reportAttributeAccessIssue]
        
        logger.info(f"MQTT listener started on topic: {config.mqtt_topic}")
        
        # Keep listener alive
        while not shutdown_event.is_set():
            await asyncio.sleep(1.0)
            
    except Exception as e:
        logger.error(f"MQTT listener error: {e}", exc_info=True)


async def run_loop(config) -> None:
    """Main run loop for m_insight process.
    
    Args:
        config: MInsightConfig instance
    """
    from .m_insight.media_insight import MediaInsight
    
    # Initialize Broadcaster
    broadcaster = MInsightBroadcaster(config)
    broadcaster.init()
    
    # Create processor with broadcaster
    processor = MediaInsight(config=config, broadcaster=broadcaster)
    
    logger.info(f"mInsight process {config.id} starting...")
    
    # Start background tasks
    mqtt_task = None
    hb_task = None
    if config.mqtt_port:
        mqtt_task = asyncio.create_task(mqtt_listener_task(config, processor))
        hb_task = asyncio.create_task(heartbeat_task(broadcaster))

    try:
        # Loop until shutdown
        while not shutdown_event.is_set():
            # Run reconciliation
            _ = await processor.run_once()
            
            # Wait for next trigger or shutdown
            # We use a combined wait to handle both MQTT triggers and exit
            trigger_task = asyncio.create_task(reconciliation_trigger.wait())
            shutdown_task = asyncio.create_task(shutdown_event.wait())
            
            done, pending = await asyncio.wait(
                [trigger_task, shutdown_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            
            # Reset trigger if it was the one that completed
            if trigger_task in done:
                reconciliation_trigger.clear()
            
            # Cleanup pending trigger/shutdown tasks
            for task in pending:
                task.cancel()
    finally:
        logger.info(f"mInsight process {config.id} shutting down...")

        # Shutdown IntelligenceProcessingService singletons
        # Shutdown MInsightProcessor resources
        await processor.shutdown()
        
        # Cancel background tasks
        if mqtt_task:
            mqtt_task.cancel()
            try:
                await mqtt_task
            except asyncio.CancelledError:
                pass
                
        if hb_task:
            hb_task.cancel()
            try:
                await hb_task
            except asyncio.CancelledError:
                pass
        
        # Final status
        broadcaster.publish_status("offline")


def main() -> int:
    """CLI entry point for m_insight worker."""
    parser = ArgumentParser(
        prog="m-insight-process",
        description="mInsight worker for image intelligence tracking",
    )
    parser.add_argument(
        "--m-insight-process-id",
        "-i",
        default="m-insight-default",
        dest="id",
        help="Unique process identifier (default: m-insight-default)",
    )
    parser.add_argument(
        "--log-level",
        "-l",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--mqtt-broker",
        "-b",
        default="localhost",
        help="MQTT broker address (default: localhost)",
    )
    parser.add_argument(
        "--mqtt-port",
        "-p",
        type=int,
        default=1883,
        help="MQTT broker port (default: 1883)",
    )
    parser.add_argument(
        "--mqtt-topic",
        "-t",
        default=None,
        help="MQTT topic for wake-up signals (default: store/{store_port}/items)",
    )
    parser.add_argument(
        "--store-port",
        type=int,
        default=8001,
        help="Port of the store service (default: 8001)",
    )
    # ML Service URLs
    parser.add_argument(
        "--auth-url",
        default="http://localhost:8010",
        help="Auth service URL",
    )
    parser.add_argument(
        "--compute-url",
        default="http://localhost:8012",
        help="Compute service URL",
    )
    parser.add_argument(
        "--compute-username",
        default="admin",
        help="Compute service username",
    )
    parser.add_argument(
        "--compute-password",
        default="admin",
        help="Compute service password",
    )
    parser.add_argument(
        "--qdrant-url",
        default="http://localhost:6333",
        help="Qdrant service URL",
    )
    parser.add_argument(
        "--qdrant-collection",
        default="image_embeddings",
        help="Qdrant collection for CLIP embeddings",
    )
    parser.add_argument(
        "--dino-collection",
        default="dino_embeddings",
        help="Qdrant collection for DINOv2 embeddings",
    )
    parser.add_argument(
        "--face-collection",
        default="face_embeddings",
        help="Qdrant collection for face embeddings",
    )
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="Disable authentication for compute service",
    )

    args = parser.parse_args(namespace=Args())

    # Initialize Config
    from .m_insight.config import MInsightConfig
    config = MInsightConfig.from_cli_args(args)
    
    # Initialize Database (Worker needs access to DB)
    from .common import database
    database.init_db(config)

    # Print startup info
    print(f"Starting m_insight process: {config.id}")
    print(f"MQTT broker: {config.mqtt_broker}:{config.mqtt_port}")
    print(f"MQTT topic: {config.mqtt_topic}")
    print(f"Log level: {args.log_level}")
    print(f"Database: {config.cl_server_dir}/store.db")
    print("Press Ctrl+C to stop\n")

    # Register signal handlers
    _ = signal.signal(signal.SIGINT, signal_handler)
    _ = signal.signal(signal.SIGTERM, signal_handler)

    # Run main loop
    try:
        asyncio.run(run_loop(config))
        return 0
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
        return 0
    except Exception as e:
        logger.error(f"Worker error: {e}", exc_info=True)
        return 1
    finally:
        # Cleanup
        from cl_ml_tools import shutdown_broadcaster
        shutdown_broadcaster()


if __name__ == "__main__":
    sys.exit(main())
