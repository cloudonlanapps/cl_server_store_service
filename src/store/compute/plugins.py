"""Plugin system integration for cl_ml_tools compute plugins."""

from cl_ml_tools import create_master_router
from cl_server_shared import Config, JobStorageService
from cl_server_shared.shared_db import JobRepositoryService

from ..auth import require_permission
from ..database import SessionLocal


def create_compute_plugin_router():
    """Create router with all registered compute plugins.

    Returns:
        tuple: (plugin_router, repository_adapter) for cleanup
    """
    # Create adapter instances
    repository_adapter = JobRepositoryService(SessionLocal)
    job_storage_service = JobStorageService(base_dir=Config.COMPUTE_STORAGE_DIR)

    # Create and mount plugin router
    plugin_router = create_master_router(
        repository=repository_adapter,
        file_storage=job_storage_service,
        get_current_user=require_permission("ai_inference_support"),
    )

    return plugin_router, repository_adapter  # Return adapter for shutdown
