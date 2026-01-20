"""Utility functions for auth service."""

import os
import sys
from pathlib import Path


def ensure_cl_server_dir(create_if_missing: bool = True) -> Path:
    """Ensure CL_SERVER_DIR exists and is writable.

    Args:
        create_if_missing: If True, create directory if it doesn't exist.
                          If False, fail if directory doesn't exist.

    Returns:
        Path to CL_SERVER_DIR

    Raises:
        SystemExit: If environment variable missing, directory missing (and not creating),
                   creation fails, or permissions invalid.
    """
    cl_server_dir = os.getenv("CL_SERVER_DIR")

    if not cl_server_dir:
        print(
            "ERROR: CL_SERVER_DIR environment variable is not set.\n"
            + "Please set it to a valid directory path.\n"
            + "Ensure the auth service is running or has been run at least once.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    dir_path = Path(cl_server_dir)

    # Check existence
    if not dir_path.exists():
        if create_if_missing:
            # Try to create directory
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
                print(f"Created CL_SERVER_DIR: {dir_path}")
            except (OSError, PermissionError) as e:
                print(
                    f"ERROR: Failed to create CL_SERVER_DIR: {dir_path}\n"
                    + f"Reason: {e}\n"
                    + "Please ensure the parent directory exists and you have write permissions.",
                    file=sys.stderr,
                )
                raise SystemExit(1)
        else:
            # Not creating, so fail
            print(
                f"ERROR: CL_SERVER_DIR does not exist: {dir_path}\n"
                + "Please ensure:\n"
                + "  1. The auth service has been started at least once, OR\n"
                + "  2. The directory has been created manually\n"
                + f"Run: mkdir -p {dir_path}",
                file=sys.stderr,
            )
            raise SystemExit(1)

    # Check if it's a directory
    if not dir_path.is_dir():
        print(
            f"ERROR: CL_SERVER_DIR is not a directory: {dir_path}\n"
            + "Please ensure CL_SERVER_DIR points to a directory, not a file.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    # Check if directory is accessible (Read & Write required for DB/Logs)
    if not os.access(dir_path, os.R_OK | os.W_OK):
        print(
            f"ERROR: CL_SERVER_DIR exists but is not accessible: {dir_path}\n"
            + "Please ensure you have read and write permissions.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    return dir_path


def get_db_url() -> str:
    cl_server_dir = ensure_cl_server_dir(create_if_missing=True)
    
    db_url = f"sqlite:///{cl_server_dir}/store.db"
    return db_url

