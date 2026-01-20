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


class Args(Namespace):
    """CLI arguments for m_insight worker."""
    
    id: str
    log_level: str
    mqtt_broker: str
    mqtt_port: int | None
    mqtt_topic: str

    def __init__(
        self,
        id: str = "m-insight-default",
        log_level: str = "INFO",
        mqtt_broker: str = "localhost",
        mqtt_port: int | None = None,
        mqtt_topic: str = "m_insight/wakeup",
    ) -> None:
        super().__init__()
        self.id = id
        self.log_level = log_level
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.mqtt_topic = mqtt_topic


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
            # Payload is ignored - just trigger reconciliation
            _ = processor.run_once()
        
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
    from .m_insight.worker import mInsight
    
    # Create processor
    processor = mInsight(config=config)
    
    logger.info(f"mInsight process {config.id} starting...")
    
    # Perform initial reconciliation
    _ = processor.run_once()
    
    # Start MQTT listener if enabled
    mqtt_task = None
    if config.mqtt_port:
        mqtt_task = asyncio.create_task(mqtt_listener_task(config, processor))
    
    try:
        # Wait for shutdown signal
        _ = await shutdown_event.wait()
    finally:
        logger.info(f"mInsight process {config.id} shutting down...")
        
        # Cancel MQTT listener
        if mqtt_task:
            _ = mqtt_task.cancel()
            try:
                await mqtt_task
            except asyncio.CancelledError:
                pass


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
        default=None,
        help="MQTT broker port (default: None, MQTT disabled)",
    )
    parser.add_argument(
        "--mqtt-topic",
        "-t",
        default="m_insight/wakeup",
        help="MQTT topic for wake-up signals (default: m_insight/wakeup)",
    )

    args = parser.parse_args(namespace=Args())

    # Initialize Config
    from .m_insight.config import MInsightConfig
    config = MInsightConfig.from_cli_args(args)
    
    # Initialize Database (Worker needs access to DB)
    from . import database
    database.init_db(config)

    # Print startup info
    print(f"Starting m_insight process: {config.id}")
    print(f"MQTT broker: {config.mqtt_broker}:{config.mqtt_port or 'disabled'}")
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
