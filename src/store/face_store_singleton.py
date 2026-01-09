"""Singleton for face embeddings Qdrant store."""

from __future__ import annotations

import logging

from qdrant_client.models import Distance

from .pysdk_config import PySDKRuntimeConfig
from .qdrant_image_store import QdrantImageStore

logger = logging.getLogger(__name__)

_face_store: QdrantImageStore | None = None


def get_face_store(config: PySDKRuntimeConfig | None = None) -> QdrantImageStore:
    """Get or create the global face store singleton (separate Qdrant collection).

    Args:
        config: PySDK runtime configuration (required on first call, optional afterwards)

    Returns:
        QdrantImageStore singleton instance for face embeddings

    Raises:
        RuntimeError: If called before initialization without config
    """
    global _face_store

    if _face_store is None:
        if config is None:
            raise RuntimeError(
                "Face store not initialized. Pass config on first call "
                "(typically done in FastAPI startup event)."
            )
        _face_store = QdrantImageStore(
            collection_name=config.face_store_collection_name,
            url=config.qdrant_url,
            vector_size=config.face_vector_size,
            distance=Distance.COSINE,  # For face similarity
            logger=logger,
        )
        logger.info(
            f"Initialized Face Store: url={config.qdrant_url}, "
            f"collection={config.face_store_collection_name}"
        )

    return _face_store
