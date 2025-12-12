"""
Versioning configuration for SQLAlchemy-Continuum.

This module MUST be imported before any models to ensure proper versioning setup.
"""
from sqlalchemy_continuum import make_versioned

# Initialize versioning BEFORE any models are imported
make_versioned(user_cls=None)
