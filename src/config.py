from __future__ import annotations

import os
from pathlib import Path

# CL_SERVER_DIR is required - root directory for all persistent data
CL_SERVER_DIR = os.getenv("CL_SERVER_DIR")
if not CL_SERVER_DIR:
    raise ValueError("CL_SERVER_DIR environment variable must be set")

# Check write permission
if not os.access(CL_SERVER_DIR, os.W_OK):
    raise ValueError(f"CL_SERVER_DIR does not exist or no write permission: {CL_SERVER_DIR}")

# Database configuration
# Derived from CL_SERVER_DIR; can be overridden with DATABASE_URL environment variable
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{CL_SERVER_DIR}/media_store.db")

# Media storage configuration
# Derived from CL_SERVER_DIR; can be overridden with MEDIA_STORAGE_DIR environment variable
MEDIA_STORAGE_DIR = os.getenv("MEDIA_STORAGE_DIR", f"{CL_SERVER_DIR}/media")

# Authentication configuration
# Path to the public key used for validating JWTs
# Derived from CL_SERVER_DIR; can be overridden with PUBLIC_KEY_PATH environment variable
PUBLIC_KEY_PATH = os.getenv("PUBLIC_KEY_PATH", f"{CL_SERVER_DIR}/public_key.pem")

# Authentication mode configuration
# Set AUTH_DISABLED=true to run in demo mode (no authentication required)
AUTH_DISABLED = os.getenv("AUTH_DISABLED", "false").lower() in ("true", "1", "yes")

# Read API authentication
# Set READ_AUTH_ENABLED=true to require authentication for read APIs
READ_AUTH_ENABLED = os.getenv("READ_AUTH_ENABLED", "false").lower() in ("true", "1", "yes")

__all__ = ["CL_SERVER_DIR", "DATABASE_URL", "MEDIA_STORAGE_DIR", "PUBLIC_KEY_PATH", "AUTH_DISABLED", "READ_AUTH_ENABLED"]


