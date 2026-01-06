"""Configuration for pysdk integration (Compute Service and Qdrant)."""

from __future__ import annotations

import os


def _get_value(key: str, default: str) -> str:
    """Get configuration value from environment with optional default."""
    return os.getenv(key, default)


def _get_int(key: str, default: int) -> int:
    """Get integer configuration value."""
    return int(os.getenv(key, str(default)))


class PySDKConfig:
    """Configuration for Compute Service and Qdrant integration."""

    # ========================================================================
    # Compute Service Configuration
    # ========================================================================

    COMPUTE_SERVICE_URL: str = _get_value("COMPUTE_SERVICE_URL", "http://localhost:8002")
    COMPUTE_USERNAME: str = _get_value("COMPUTE_USERNAME", "admin")
    COMPUTE_PASSWORD: str = _get_value("COMPUTE_PASSWORD", "admin")

    # ========================================================================
    # Qdrant Configuration
    # ========================================================================

    QDRANT_URL: str = _get_value("QDRANT_URL", "http://localhost:6333")
    QDRANT_COLLECTION_NAME: str = _get_value("QDRANT_COLLECTION_NAME", "image_embeddings")
