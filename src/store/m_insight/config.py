from __future__ import annotations

from pydantic import Field

from ..common.config import BaseConfig


class MInsightConfig(BaseConfig):
    """Unified mInsight configuration and CLI arguments."""

    # CLI Fields (mapped to Args)
    id: str = "m-insight-default"
    log_level: str = "INFO"
    store_port: int = 8001

    # CLI-only fields for argparse to populate
    auth_url: str | None = None
    compute_url: str | None = None
    compute_username: str = "admin"
    compute_password: str = "admin"
    mqtt_topic_raw: str | None = Field(default=None, alias="mqtt_topic")

    # Worker processing settings (non-CLI defaults)
    face_vector_size: int = 512
    face_embedding_threshold: float = 0.7

    # Actual internal state
    auth_service_url: str = "http://localhost:8010"
    compute_service_url: str = "http://localhost:8012"
    mqtt_topic: str = "m_insight/wakeup"

    def finalize(self):
        """Finalize configuration after CLI parsing."""
        # 1. Base finalization (paths, basic auth/mqtt, shared collections)
        self.finalize_base()

        # 2. Sync CLI URLs to internal URLs
        if self.auth_url:
            self.auth_service_url = self.auth_url
        if self.compute_url:
            self.compute_service_url = self.compute_url

        # 3. Handle MQTT topic logic
        if self.mqtt_topic_raw:
            self.mqtt_topic = self.mqtt_topic_raw
        elif not self.mqtt_topic or self.mqtt_topic == "m_insight/wakeup":
            # Default pattern if not explicitly set
            self.mqtt_topic = f"store/{self.store_port}/items"
