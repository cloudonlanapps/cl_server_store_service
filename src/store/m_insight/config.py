from ..common.config import BaseConfig


class MInsightConfig(BaseConfig):
    """Unified mInsight configuration and CLI arguments."""

    # CLI Fields (mapped to Args)
    id: str
    log_level: str
    store_port: int

    # External Service URLs
    auth_url: str
    compute_url: str
    compute_username: str
    compute_password: str

    # Worker processing settings (non-CLI defaults)
    face_vector_size: int
    face_embedding_threshold: float

    # MQTT configuration
    mqtt_topic: str
