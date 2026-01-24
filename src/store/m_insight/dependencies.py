from fastapi import Depends

from store.store.config import StoreConfig


from store.store.dependencies import get_config


from store.db_service import DBService

def get_db_service() -> DBService:
    """Dependency to get DBService instance."""
    from store.db_service import database
    if database.SessionLocal is None:
        database.init_db()
    return DBService()


from store.vectorstore_services.vector_stores import (
    QdrantVectorStore,
    get_clip_store,
    get_dino_store,
    get_face_store,
)

def get_clip_store_dep(
    config: StoreConfig = Depends(get_config),
) -> QdrantVectorStore:
    """Dependency to get CLIP vector store."""
    return get_clip_store(
        url=config.qdrant_url,
        collection_name=config.qdrant_collection,
    )

def get_dino_store_dep(
    config: StoreConfig = Depends(get_config),
) -> QdrantVectorStore:
    """Dependency to get DINO vector store."""
    return get_dino_store(
        url=config.qdrant_url,
        collection_name=config.dino_collection,
    )

def get_face_store_dep(
    config: StoreConfig = Depends(get_config),
) -> QdrantVectorStore:
    """Dependency to get Face vector store."""
    return get_face_store(
        url=config.qdrant_url,
        collection_name=config.face_collection,
        vector_size=getattr(config, "face_vector_size", 512),
    )
