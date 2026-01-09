"""Configuration for pysdk integration (Compute Service and Qdrant)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PySDKRuntimeConfig(BaseModel):
    """Runtime configuration for PySDK integration (Pydantic model).

    This configuration is initialized from CLI arguments passed to main.py,
    not from environment variables.
    """

    # ========================================================================
    # Auth Service Configuration
    # ========================================================================

    auth_service_url: str = Field(
        default="http://localhost:8000",
        description="Auth service URL"
    )

    # ========================================================================
    # Compute Service Configuration
    # ========================================================================

    compute_service_url: str = Field(
        default="http://localhost:8002",
        description="Compute service URL"
    )
    compute_username: str = Field(
        default="admin",
        description="Compute service username"
    )
    compute_password: str = Field(
        default="admin",
        description="Compute service password"
    )

    # ========================================================================
    # Qdrant Configuration
    # ========================================================================

    qdrant_url: str = Field(
        default="http://localhost:6333",
        description="Qdrant vector database URL"
    )
    qdrant_collection_name: str = Field(
        default="image_embeddings",
        description="Qdrant collection name for CLIP embeddings"
    )

    # ========================================================================
    # Face Store Configuration
    # ========================================================================

    face_store_collection_name: str = Field(
        default="face_embeddings",
        description="Qdrant collection name for face embeddings"
    )
    face_vector_size: int = Field(
        default=512,
        description="Face embedding vector dimension"
    )
    face_embedding_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Similarity threshold for face matching (0.0-1.0)"
    )
