"""Compute job management module.

This module handles:
- Job lifecycle management (create, retrieve, delete)
- Worker capability discovery via MQTT
- Plugin system integration (cl_ml_tools)
- Storage management for compute jobs
"""

from .capability_manager import close_capability_manager, get_capability_manager
from .models import Job, QueueEntry
from .plugins import create_compute_plugin_router
from .routes import router as compute_router
from .schemas import CleanupResult, JobResponse, StorageInfo
from .service import CapabilityService, JobService

__all__ = [
    "Job",
    "QueueEntry",
    "JobService",
    "CapabilityService",
    "JobResponse",
    "StorageInfo",
    "CleanupResult",
    "compute_router",
    "create_compute_plugin_router",
    "get_capability_manager",
    "close_capability_manager",
]
