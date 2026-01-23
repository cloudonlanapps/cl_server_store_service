"""
Versioning configuration for SQLAlchemy-Continuum.

This module MUST be imported before any models to ensure proper versioning setup.
"""

from sqlalchemy_continuum import make_versioned
from sqlalchemy_continuum.plugins import (  # pyright: ignore[reportMissingTypeStubs]
    TransactionChangesPlugin,
)

# Initialize versioning BEFORE any models are imported
# Use TransactionChangesPlugin to track changes
make_versioned(user_cls=None, plugins=[TransactionChangesPlugin()])  # pyright: ignore[reportCallIssue]
