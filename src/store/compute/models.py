"""Compute job models.

Re-exports Job and QueueEntry models from cl_server_shared.
These models are shared between store and worker services.
"""

from cl_server_shared.models import Job, QueueEntry

__all__ = ["Job", "QueueEntry"]
