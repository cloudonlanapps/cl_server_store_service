"""Compute job management routes."""

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from .. import auth
from ..database import get_db
from . import schemas, service

router = APIRouter()


@router.get(
    "/jobs/{job_id}",
    tags=["job"],
    summary="Get Job Status",
    description="Get job status and results.",
    operation_id="get_job",
    responses={200: {"model": schemas.JobResponse, "description": "Job found"}},
)
async def get_job(
    job_id: str = Path(..., title="Job ID"),
    db: Session = Depends(get_db),
    user: dict | None = Depends(auth.require_permission("ai_inference_support")),
) -> schemas.JobResponse:
    """Get job status and results."""
    job_service = service.JobService(db)
    return job_service.get_job(job_id)


@router.delete(
    "/jobs/{job_id}",
    tags=["job"],
    summary="Delete Job",
    description="Delete job and all associated files.",
    operation_id="delete_job",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_job(
    job_id: str = Path(..., title="Job ID"),
    db: Session = Depends(get_db),
    user: dict | None = Depends(auth.require_permission("ai_inference_support")),
):
    """Delete job and all associated files."""
    job_service = service.JobService(db)
    job_service.delete_job(job_id)
    # No return statement - FastAPI will return 204 automatically


@router.get(
    "/admin/jobs/storage/size",
    tags=["admin"],
    summary="Get Storage Size",
    description="Get total storage usage (admin only).",
    operation_id="get_storage_size",
    responses={200: {"model": schemas.StorageInfo, "description": "Storage information"}},
)
async def get_storage_size(
    db: Session = Depends(get_db),
    user: dict | None = Depends(auth.require_admin),
) -> schemas.StorageInfo:
    """Get total storage usage (admin only)."""
    job_service = service.JobService(db)
    return job_service.get_storage_size()


@router.delete(
    "/admin/jobs/cleanup",
    tags=["admin"],
    summary="Cleanup Old Jobs",
    description="Clean up jobs older than specified number of days (admin only).",
    operation_id="cleanup_old_jobs",
    responses={200: {"model": schemas.CleanupResult, "description": "Cleanup results"}},
)
async def cleanup_old_jobs(
    days: int = Query(7, ge=0, description="Delete jobs older than N days"),
    db: Session = Depends(get_db),
    user: dict | None = Depends(auth.require_admin),
) -> schemas.CleanupResult:
    """Clean up jobs older than specified number of days (admin only)."""
    job_service = service.JobService(db)
    return job_service.cleanup_old_jobs(days)


@router.get(
    "/capabilities",
    tags=["compute"],
    summary="Get Worker Capabilities",
    description="Returns available worker capabilities and their available counts",
    response_model=dict,
    operation_id="get_worker_capabilities",
)
async def get_worker_capabilities(
    db: Session = Depends(get_db),
) -> dict:
    """Get available worker capabilities and counts from connected workers.

    Returns a dictionary with:
    - num_workers: Total number of connected workers (0 if none available)
    - capabilities: Dictionary mapping capability names to available worker counts

    Example response:
    {
        "num_workers": 3,
        "capabilities": {
            "image_resize": 2,
            "image_conversion": 1
        }
    }
    """
    capability_service = service.CapabilityService(db)
    capabilities = capability_service.get_available_capabilities()
    num_workers = capability_service.get_worker_count()
    return {
        "num_workers": num_workers,
        "capabilities": capabilities,
    }

    @router.get(
        "/compute/jobs/{job_id}",
        tags=["job"],
        summary="Get Job Status",
        description="Get job status and results.",
        operation_id="get_job",
        responses={200: {"model": schemas.JobResponse, "description": "Job found"}},
    )
    async def get_job(
        job_id: str = Path(..., title="Job ID"),
        db: Session = Depends(get_db),
        user: dict | None = Depends(auth.require_permission("ai_inference_support")),
    ) -> schemas.JobResponse:
        """Get job status and results."""
        job_service = service.JobService(db)
        return job_service.get_job(job_id)

    @router.delete(
        "/compute/jobs/{job_id}",
        tags=["job"],
        summary="Delete Job",
        description="Delete job and all associated files.",
        operation_id="delete_job",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def delete_job(
        job_id: str = Path(..., title="Job ID"),
        db: Session = Depends(get_db),
        user: dict | None = Depends(auth.require_permission("ai_inference_support")),
    ):
        """Delete job and all associated files."""
        job_service = service.JobService(db)
        job_service.delete_job(job_id)
        # No return statement - FastAPI will return 204 automatically

    @router.get(
        "/admin/compute/jobs/storage/size",
        tags=["admin"],
        summary="Get Storage Size",
        description="Get total storage usage (admin only).",
        operation_id="get_storage_size",
        responses={200: {"model": schemas.StorageInfo, "description": "Storage information"}},
    )
    async def get_storage_size(
        db: Session = Depends(get_db),
        user: dict | None = Depends(auth.require_admin),
    ) -> schemas.StorageInfo:
        """Get total storage usage (admin only)."""
        job_service = service.JobService(db)
        return job_service.get_storage_size()

    @router.delete(
        "/admin/compute/jobs/cleanup",
        tags=["admin"],
        summary="Cleanup Old Jobs",
        description="Clean up jobs older than specified number of days (admin only).",
        operation_id="cleanup_old_jobs",
        responses={200: {"model": schemas.CleanupResult, "description": "Cleanup results"}},
    )
    async def cleanup_old_jobs(
        days: int = Query(7, ge=0, description="Delete jobs older than N days"),
        db: Session = Depends(get_db),
        user: dict | None = Depends(auth.require_admin),
    ) -> schemas.CleanupResult:
        """Clean up jobs older than specified number of days (admin only)."""
        job_service = service.JobService(db)
        return job_service.cleanup_old_jobs(days)

    @router.get(
        "/compute/capabilities",
        tags=["compute"],
        summary="Get Worker Capabilities",
        description="Returns available worker capabilities and their available counts",
        response_model=dict,
        operation_id="get_worker_capabilities",
    )
    async def get_worker_capabilities(
        db: Session = Depends(get_db),
    ) -> dict:
        """Get available worker capabilities and counts from connected workers.

        Returns a dictionary with:
        - num_workers: Total number of connected workers (0 if none available)
        - capabilities: Dictionary mapping capability names to available worker counts

        Example response:
        {
            "num_workers": 3,
            "capabilities": {
                "image_resize": 2,
                "image_conversion": 1
            }
        }
        """
        capability_service = service.CapabilityService(db)
        capabilities = capability_service.get_available_capabilities()
        num_workers = capability_service.get_worker_count()
        return {
            "num_workers": num_workers,
            "capabilities": capabilities,
        }
