from __future__ import annotations

import json
import time
from typing import Any, Dict

from cl_ml_tools import get_broadcaster
from loguru import logger


class MInsightMonitor:
    """Monitors MInsight process status via MQTT."""

    def __init__(self, config: Any):
        self.config = config
        self.broadcaster = None
        self.statuses: Dict[int, Dict[str, Any]] = {}  # port -> status dict

    def start(self):
        """Start monitoring."""
        if not self.config.mqtt_port:
            logger.warning("MQTT disabled, MInsightMonitor not starting")
            return

        try:
            self.broadcaster = get_broadcaster(
                broadcast_type="mqtt",
                broker=self.config.mqtt_server,
                port=self.config.mqtt_port,
            )

            # Access underlying Paho client
            if hasattr(self.broadcaster, "client"):
                client = self.broadcaster.client
                client.on_message = self._on_message
                
                # Subscribe to topics
                # mInsight/<port>/started -> reconciling
                # mInsight/<port>/ended -> completed/idle
                # mInsight/<port>/status -> heartbeat (running/offline)
                client.subscribe("mInsight/+/started")
                client.subscribe("mInsight/+/ended")
                client.subscribe("mInsight/+/status")
                
                # Start background loop if not already started by cl_ml_tools
                # Note: cl_ml_tools might start it, but calling loop_start again is generally safe/idempotent in Paho
                # if checking internal state, but safer to just let it be if it works.
                # However, to be sure we receive messages in this process:
                client.loop_start()
                
                logger.info("MInsightMonitor started listening on MQTT")
        except Exception as e:
            logger.error(f"Failed to start MInsightMonitor: {e}")

    def stop(self):
        """Stop monitoring."""
        if self.broadcaster and hasattr(self.broadcaster, "client"):
            try:
                self.broadcaster.client.loop_stop()
                self.broadcaster.client.disconnect()
            except Exception as e:
                logger.error(f"Error stopping MInsightMonitor: {e}")

    def _on_message(self, client: Any, userdata: Any, msg: Any):
        """Handle incoming MQTT messages."""
        try:
            topic = msg.topic  # mInsight/<port>/<type>
            parts = topic.split("/")
            if len(parts) < 3:
                return

            # parts[0] = "mInsight"
            port_str = parts[1]
            msg_type = parts[2]

            try:
                port = int(port_str)
            except ValueError:
                return

            try:
                payload = json.loads(msg.payload.decode())
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON payload on {topic}")
                return

            if port not in self.statuses:
                self.statuses[port] = {
                    "status": "unknown",
                    "last_update": 0,
                    "port": port
                }
            
            # Update generic metadata
            current_time = int(time.time() * 1000)
            self.statuses[port]["last_update"] = current_time
            self.statuses[port].update(payload)

            # Update derived status based on message type
            if msg_type == "status":
                # Heartbeat payload usually contains "status" field
                pass
            elif msg_type == "started":
                self.statuses[port]["status"] = "running"
            elif msg_type == "ended":
                self.statuses[port]["status"] = "idle"

        except Exception as e:
            logger.error(f"Error processing monitor message: {e}")

    def get_status(self, port: int | None = None) -> Dict[str, Any] | Dict[int, Dict[str, Any]]:
        """
        Get status for a specific port or all known ports.
        
        Args:
            port: Optional specific port to query
            
        Returns:
            Status dictionary or dictionary of all statuses keyed by port
        """
        if port is not None:
            return self.statuses.get(port, {"status": "unknown"})
        return self.statuses
