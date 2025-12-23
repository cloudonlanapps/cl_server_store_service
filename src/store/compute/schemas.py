"""Compute job response schemas."""

from __future__ import annotations

from cl_ml_tools import Job as BaseJob
from pydantic import BaseModel, Field


class JobResponse(BaseJob):
    """Response schema for job information.

    Extends the library's Job schema with service-specific fields
    for timestamps and priority.
    """

    priority: int = Field(5, description="Job priority (0-10)")
    created_at: int = Field(..., description="Job creation timestamp (milliseconds)")
    updated_at: int | None = Field(None, description="Job last update timestamp (milliseconds)")
    started_at: int | None = Field(None, description="Job start timestamp (milliseconds)")
    completed_at: int | None = Field(None, description="Job completion timestamp (milliseconds)")


class StorageInfo(BaseModel):
    """Response schema for storage information."""

    total_size: int = Field(..., description="Total storage usage in bytes")
    job_count: int = Field(..., description="Number of jobs stored")


class CleanupResult(BaseModel):
    """Response schema for cleanup operation results."""

    deleted_count: int = Field(..., description="Number of jobs deleted")
    freed_space: int = Field(..., description="Space freed in bytes")
