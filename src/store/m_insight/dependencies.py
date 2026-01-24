from fastapi import Depends
from sqlalchemy.orm import Session

from store.db_service.db_internals import get_db
from store.m_insight.retrieval_service import IntelligenceRetrieveService
from store.store.config import StoreConfig


from store.store.dependencies import get_config


def get_intelligence_service(
    db: Session = Depends(get_db),
    config: StoreConfig = Depends(get_config),
) -> IntelligenceRetrieveService:
    """Dependency to get IntelligenceRetrieveService instance.

    This creates a new service instance per request (because db is request-scoped),
    but internally reuse singleton vector stores.
    """
    return IntelligenceRetrieveService(db, config)
