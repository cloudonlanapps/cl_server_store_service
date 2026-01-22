from fastapi import Depends, Request
from sqlalchemy.orm import Session

from store.common.database import get_db
from store.store.config import StoreConfig
from store.m_insight.retrieval_service import IntelligenceRetrieveService


def get_config(request: Request) -> StoreConfig:
    """Dependency to get StoreConfig from app state."""
    return request.app.state.config


def get_intelligence_service(
    db: Session = Depends(get_db),
    config: StoreConfig = Depends(get_config),
) -> IntelligenceRetrieveService:
    """Dependency to get IntelligenceRetrieveService instance.
    
    This creates a new service instance per request (because db is request-scoped),
    but internally reuse singleton vector stores.
    """
    return IntelligenceRetrieveService(db, config)
