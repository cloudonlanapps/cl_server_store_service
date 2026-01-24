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
from argparse import ArgumentParser
from types import FrameType

from loguru import logger

from store.m_insight import MediaInsight, MInsightConfig

from .m_insight.broadcaster import MInsightBroadcaster
from cl_ml_tools import get_broadcaster, shutdown_broadcaster
from .common import utils
from .db_service.db_internals import database
from .m_insight.config import MInsightConfig

# Global shutdown event and signal counter
shutdown_event = asyncio.Event()
reconciliation_trigger = asyncio.Event()
shutdown_signal_count = 0


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


async def heartbeat_task(broadcaster: MInsightBroadcaster):
    """Periodic heartbeat task."""
    try:
        while not shutdown_event.is_set():
            broadcaster.publish_status("running")
            await asyncio.sleep(5)  # 5 second heartbeat
    except asyncio.CancelledError:
        pass


async def mqtt_listener_task(config: MInsightConfig) -> None:
    """Background task to listen for MQTT wake-up signals.

    Args:
        config: MInsightConfig instance
        processor: mInsight instance
    """
    if not config.mqtt_port:
        logger.info("MQTT disabled, skipping listener")
        return

    try:
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
        if not broadcaster or not broadcaster.client:
            raise ValueError("Broadcaster not initialized")
        _ = broadcaster.client.subscribe(config.mqtt_topic)
        broadcaster.client.on_message = on_message

        logger.info(f"MQTT listener started on topic: {config.mqtt_topic}")

        # Keep listener alive
        while not shutdown_event.is_set():
            await asyncio.sleep(1.0)

    except Exception as e:
        logger.error(f"MQTT listener error: {e}", exc_info=True)


async def run_loop(config: MInsightConfig) -> None:
    """Main run loop for m_insight process.

    Args:
        config: MInsightConfig instance
    """

    # Initialize Broadcaster
    broadcaster = MInsightBroadcaster(config)
    broadcaster.init()

    # Create processor with broadcaster
    processor = MediaInsight(config=config, broadcaster=broadcaster)

    logger.info(f"mInsight process {config.id} starting...")

    if not config.mqtt_port:
        raise ValueError("MQTT port is not set")

    # Start background tasks
    mqtt_task = asyncio.create_task(mqtt_listener_task(config))
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
                _ = task.cancel()
    finally:
        logger.info(f"mInsight process {config.id} shutting down...")

        # Shutdown IntelligenceProcessingService singletons
        # Shutdown MInsightProcessor resources
        await processor.shutdown()

        # Cancel background tasks
        if mqtt_task:
            _ = mqtt_task.cancel()
            try:
                await mqtt_task
            except asyncio.CancelledError:
                pass

        if hb_task:
            _ = hb_task.cancel()
            try:
                await hb_task
            except asyncio.CancelledError:
                pass

        # Final status
        broadcaster.publish_status("offline")


def main() -> int:
    """CLI entry point for m_insight worker."""
    _ = parser = ArgumentParser(
        prog="m-insight-process",
        description="mInsight worker for image intelligence tracking",
    )
    _ = parser.add_argument(
        "--m-insight-process-id",
        "-i",
        default="m-insight-default",
        dest="id",
        help="Unique process identifier (default: m-insight-default)",
    )
    _ = parser.add_argument(
        "--log-level",
        "-l",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    _ = parser.add_argument(
        "--mqtt-broker",
        "-b",
        default="localhost",
        help="MQTT broker address (default: localhost)",
    )
    _ = parser.add_argument(
        "--mqtt-port",
        "-p",
        type=int,
        default=1883,
        help="MQTT broker port (default: 1883)",
    )
    _ = parser.add_argument(
        "--mqtt-topic",
        "-t",
        default=None,
        help="MQTT topic for wake-up signals (default: store/{store_port}/items)",
    )
    _ = parser.add_argument(
        "--store-port",
        type=int,
        default=8001,
        help="Port of the store service (default: 8001)",
    )
    # ML Service URLs
    _ = parser.add_argument(
        "--auth-url",
        default="http://localhost:8010",
        help="Auth service URL",
    )
    _ = parser.add_argument(
        "--compute-url",
        default="http://localhost:8012",
        help="Compute service URL",
    )
    _ = parser.add_argument(
        "--compute-username",
        default="admin",
        help="Compute service username",
    )
    _ = parser.add_argument(
        "--compute-password",
        default="admin",
        help="Compute service password",
    )
    _ = parser.add_argument(
        "--qdrant-url",
        default="http://localhost:6333",
        help="Qdrant service URL",
    )
    _ = parser.add_argument(
        "--qdrant-collection",
        default="clip_embeddings",
        help="Qdrant collection for CLIP embeddings",
    )
    _ = parser.add_argument(
        "--dino-collection",
        default="dino_embeddings",
        help="Qdrant collection for DINOv2 embeddings",
    )
    _ = parser.add_argument(
        "--face-collection",
        default="face_embeddings",
        help="Qdrant collection for face embeddings",
    )
    _ = parser.add_argument(
        "--no-auth",
        action="store_true",
        help="Disable authentication for compute service",
    )
    args = parser.parse_args()

    # Initialize Database (Worker needs access to DB)

    # Initialize basic info needed for config
    cl_dir = utils.ensure_cl_server_dir(create_if_missing=True)

    # Convert args to dict and add required path keys
    config_dict = {k: v for k, v in vars(args).items() if v is not None}
    config_dict["cl_server_dir"] = cl_dir
    config_dict["media_storage_dir"] = cl_dir / "media"
    config_dict["public_key_path"] = cl_dir / "keys" / "public_key.pem"

    config = MInsightConfig.model_validate(config_dict)
    config.finalize()

    # Print startup info
    print(f"Starting m_insight process: {config.id}")
    print(f"MQTT broker: {config.mqtt_broker}:{config.mqtt_port}")
    print(f"MQTT topic: {config.mqtt_topic}")
    print(f"Log level: {config.log_level}")
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
        shutdown_broadcaster()


if __name__ == "__main__":
    sys.exit(main())
