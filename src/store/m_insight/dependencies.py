from fastapi import Depends

from store.m_insight.retrieval_service import IntelligenceRetrieveService
from store.store.config import StoreConfig


from store.store.dependencies import get_config


def get_intelligence_service(
    config: StoreConfig = Depends(get_config),
) -> IntelligenceRetrieveService:
    """Dependency to get IntelligenceRetrieveService instance.

    This creates a new service instance per request,
    but internally reuse singleton vector stores.
    """
    return IntelligenceRetrieveService(config)
