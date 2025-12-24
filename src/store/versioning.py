"""
Versioning configuration for SQLAlchemy-Continuum.

This module MUST be imported before any models to ensure proper versioning setup.
"""

from sqlalchemy_continuum import (  # pyright: ignore[reportMissingTypeStubs]
    make_versioned,  # pyright: ignore[reportUnknownVariableType]
)

# Initialize versioning BEFORE any models are imported
make_versioned(user_cls=None)  # pyright: ignore[reportArgumentType]
