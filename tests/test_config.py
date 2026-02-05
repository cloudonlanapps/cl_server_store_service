"""
Test configuration for media store tests.

This module provides centralized configuration for all tests, including:
- Test image file paths (absolute paths)
- Test file loading from test_files.txt
- Configuration constants
"""

import os
from pathlib import Path

# Get the absolute path to the tests directory
TESTS_DIR = Path(__file__).parent.absolute()

# TEST_VECTORS_DIR: Root of test media files (images, etc)
# Default: ~/Work/cl_server_test_media
# Can be overridden by TEST_VECTORS_DIR env var
TEST_VECTORS_DIR = Path(os.getenv("TEST_VECTORS_DIR", str(Path.home() / "cl_server_test_media")))

# IMAGES_DIR: Directory containing images within test vectors
IMAGES_DIR = TEST_VECTORS_DIR / "images"

# Test files list path
TEST_FILES_LIST = TESTS_DIR / "test_files.txt"

# Test artifacts directory
# Default: /tmp/cl_server_test_artifacts
# Can be overridden by TEST_ARTIFACT_DIR env var
TEST_ARTIFACT_DIR_ROOT = Path(os.getenv("TEST_ARTIFACT_DIR", "/tmp/cl_server_test_artifacts"))
TEST_ARTIFACTS_DIR = TEST_ARTIFACT_DIR_ROOT / "store" / "data"

# Legacy alias (if used elsewhere)
TEST_DATA_DIR = TEST_ARTIFACTS_DIR


def load_test_files() -> list[Path]:
    """
    Load test file paths from test_files.txt.

    Paths in test_files.txt should be relative to TEST_VECTORS_DIR.
    If absolute path provided, it's used as is (compatibility).

    Returns:
        List of absolute Path objects for test images (existence not validated)

    Note: File existence is NOT validated here to avoid slow I/O during import.
    Individual tests will fail if files are missing when they try to use them.
    """
    if not TEST_FILES_LIST.exists():
        return []

    test_files = []
    with open(TEST_FILES_LIST) as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Convert to Path object
            p = Path(line)

            if p.is_absolute():
                file_path = p
            else:
                # Resolve relative to TEST_VECTORS_DIR
                file_path = TEST_VECTORS_DIR / p

            # Add path without checking existence - tests will fail if missing
            test_files.append(file_path.absolute())

    return test_files


def get_all_test_images() -> list[Path]:
    """
    Get all available test images.

    Loads test file paths from test_files.txt.

    Returns:
        List of absolute Path objects for test images (existence not validated)

    Note: File existence is NOT validated here to avoid slow I/O during import.
    Individual tests will fail if files are missing when they try to use them.
    """
    # Strictly load from test_files.txt
    return load_test_files()


# Pre-load test images for convenience
# Note: This is fast now since we don't validate file existence
TEST_IMAGES = get_all_test_images()

# Specific test images (if available)
PRIMARY_TEST_IMAGE = TEST_IMAGES[0] if len(TEST_IMAGES) > 0 else None
SECONDARY_TEST_IMAGE = TEST_IMAGES[1] if len(TEST_IMAGES) > 1 else None
TERTIARY_TEST_IMAGE = TEST_IMAGES[2] if len(TEST_IMAGES) > 2 else None

# Test configuration constants
TEST_DB_URL = "sqlite:///:memory:"

__all__ = [
    "TESTS_DIR",
    "TEST_VECTORS_DIR",
    "IMAGES_DIR",
    "TEST_FILES_LIST",
    "TEST_ARTIFACTS_DIR",
    "TEST_DATA_DIR",
    "TEST_IMAGES",
    "PRIMARY_TEST_IMAGE",
    "SECONDARY_TEST_IMAGE",
    "TERTIARY_TEST_IMAGE",
    "TEST_DB_URL",
    "load_test_files",
    "get_all_test_images",
]
