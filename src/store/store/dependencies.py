from __future__ import annotations
from fastapi import Depends, Request
from sqlalchemy.orm import Session
from typing import cast # Added for type casting

from store.db_service import DBService
from store.db_service.dependencies import get_db_service
from store.db_service.db_internals import get_db
from store.db_service.config import ConfigDBService
from store.vectorstore_services.vector_stores import (
    QdrantVectorStore,
    get_clip_store_dep,
    get_dino_store_dep,
    get_face_store_dep,
)
from store.common.storage import StorageService
from ..broadcast_service.broadcaster import MInsightBroadcaster

from .config import StoreConfig
from store.broadcast_service.monitor import MInsightMonitor
from store.m_insight.job_service import JobSubmissionService
from .service import EntityService




def get_config_service(db: DBService = Depends(get_db_service)) -> ConfigDBService:
    """Dependency to get ConfigDBService instance."""
    return db.config




def get_m_insight_broadcaster(request: Request) -> MInsightBroadcaster | None:
    """Dependency to get MInsightBroadcaster from app state."""
    return cast(MInsightBroadcaster | None, getattr(request.app.state, "broadcaster", None))


def get_monitor(request: Request) -> MInsightMonitor | None:
    """Dependency to get monitor from app state."""
    return getattr(request.app.state, "monitor", None)  # pyright: ignore[reportAny]


def get_job_submission_service(
    config: StoreConfig = Depends(StoreConfig.get_config),
    broadcaster: MInsightBroadcaster | None = Depends(get_m_insight_broadcaster),
    db_service: DBService = Depends(get_db_service),
) -> JobSubmissionService | None:
    """Dependency to get JobSubmissionService instance for the API.
    
    This initializes a ComputeClient on demand if credentials are provided.
    """
    if not config.compute_url or not config.compute_username or not config.compute_password:
        return None
        
    from cl_client import ComputeClient, ServerPref, SessionManager
    
    # We use a simple one-off client for the API
    # In a production scenario, we might want to pool or cache this session
    server_config = ServerPref(
        auth_url=config.auth_url or "http://localhost:8010",
        compute_url=config.compute_url,
        mqtt_url=config.mqtt_url,
    )
    
    # Create session manager but don't login every time if we can avoid it
    # For now, we follow the pattern of MediaInsight initialize
    async def _get_client():
        session = SessionManager(server_pref=server_config)
        await session.login(
            username=config.compute_username,
            password=config.compute_password,
        )
        return session.create_compute_client()

    # NOTE: Since this is a synchronous dependency, we might have issues if we need to call async login.
    # Actually, FastAPI dependencies can be async.
    
    return None # Placeholder for now, will refactor to async if needed

async def get_job_submission_service_async(
    config: StoreConfig = Depends(StoreConfig.get_config),
    broadcaster: MInsightBroadcaster | None = Depends(get_m_insight_broadcaster),
    db_service: DBService = Depends(get_db_service),
) -> JobSubmissionService | None:
    """Async dependency to get JobSubmissionService instance for the API."""
    if not config.compute_url or not config.compute_username or not config.compute_password:
        return None
        
    from cl_client import ServerPref, SessionManager
    
    server_config = ServerPref(
        auth_url=config.auth_url or "http://localhost:8010",
        compute_url=config.compute_url,
        mqtt_url=config.mqtt_url,
    )
    
    storage_service = StorageService(base_dir=str(config.media_storage_dir))
    
    # Create session and login
    session = SessionManager(server_pref=server_config)
    await session.login(
        username=config.compute_username,
        password=config.compute_password,
    )
    compute_client = session.create_compute_client()
    
    return JobSubmissionService(
        compute_client=compute_client,
        storage_service=storage_service,
        broadcaster=broadcaster,
        db=db_service,
    )


def get_entity_service(
    db: Session = Depends(get_db),
    config: StoreConfig = Depends(StoreConfig.get_config),
    db_service: DBService = Depends(get_db_service),
    clip_store: QdrantVectorStore = Depends(get_clip_store_dep),
    dino_store: QdrantVectorStore = Depends(get_dino_store_dep),
    face_store: QdrantVectorStore = Depends(get_face_store_dep),
    broadcaster: MInsightBroadcaster | None = Depends(get_m_insight_broadcaster),
    job_service: JobSubmissionService | None = Depends(get_job_submission_service_async),
) -> EntityService:
    """Dependency to get EntityService instance."""
    from .face_service import FaceService

    db_service_with_session = DBService(db=db)
    storage_service = StorageService(base_dir=str(config.media_storage_dir))
    face_service = FaceService(
        db=db,
        db_service=db_service_with_session,
        face_store=face_store,
        storage_service=storage_service,
    )

    return EntityService(
        db,
        config,
        face_service=face_service,
        clip_store=clip_store,
        dino_store=dino_store,
        broadcaster=broadcaster,
        job_service=job_service,
    )
