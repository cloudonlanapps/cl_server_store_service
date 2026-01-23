from __future__ import annotations

from typing import cast

from cl_ml_tools import BroadcasterBase, get_broadcaster
from loguru import logger

from store.common.schemas import MInsightStatus

from .config import StoreConfig


class MInsightMonitor:
    """Monitors MInsight process status via MQTT for the configured store port."""

    def __init__(self, config: StoreConfig):
        self.config: StoreConfig = config
        self.broadcaster: BroadcasterBase | None = None
        self.process_status: MInsightStatus | None = None

    def start(self) -> None:
        """Start monitoring."""
        if not self.config.mqtt_port:
            logger.warning("MQTT disabled, MInsightMonitor not starting")
            return

        try:
            self.broadcaster = get_broadcaster(
                broadcast_type="mqtt",
                broker=self.config.mqtt_broker,
                port=self.config.mqtt_port,
            )

            # Access underlying Paho client
            client = getattr(self.broadcaster, "client", None)
            if client:
                client.on_message = self._on_message

                # Subscribe to unified status topic
                port = self.config.port
                _ = cast(object, client.subscribe(f"mInsight/{port}/status"))  # pyright: ignore[reportAny]

                # Start background loop
                _ = cast(object, client.loop_start())  # pyright: ignore[reportAny]

                logger.info(f"MInsightMonitor started listening on MQTT for port {port}")
        except Exception as e:
            logger.error(f"Failed to start MInsightMonitor: {e}")

    def stop(self) -> None:
        """Stop monitoring."""
        if self.broadcaster:
            client = getattr(self.broadcaster, "client", None)
            if client:
                try:
                    _ = cast(object, client.loop_stop())  # pyright: ignore[reportAny]
                    _ = cast(object, client.disconnect())  # pyright: ignore[reportAny]
                except Exception as e:
                    logger.error(f"Error stopping MInsightMonitor: {e}")

    def _on_message(self, client: object, userdata: object, msg: object) -> None:
        """Handle incoming MQTT messages."""
        _ = client
        _ = userdata
        try:
            topic = cast(str, getattr(msg, "topic"))  # mInsight/<port>/status
            parts = topic.split("/")
            if len(parts) < 3:
                return

            # parts[0] = "mInsight", parts[1] = <port>, parts[2] = status
            try:
                msg_port = int(parts[1])
            except ValueError:
                return

            if msg_port != self.config.port:
                return

            payload_bytes = cast(bytes, getattr(msg, "payload"))

            try:
                self.process_status = MInsightStatus.model_validate_json(payload_bytes)
            except Exception as ve:
                logger.warning(f"Payload validation failed for {topic}: {ve}")
                return

        except Exception as e:
            logger.error(f"Error processing monitor message: {e}")

    def get_status(self) -> MInsightStatus | None:
        """Get the monitored process status."""
        return self.process_status
