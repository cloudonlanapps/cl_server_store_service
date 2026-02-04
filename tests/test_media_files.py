"""
Test image file paths loader.

Loads test image/video file paths from test_files.txt.
"""

from pathlib import Path
from .test_config import TEST_VECTORS_DIR


def get_test_media_files():
    """
    Get list of test media files as Path objects from test_files.txt.
    
    Returns:
        List of Path objects for files that exist.
        Skips files that don't exist with a warning.
    """
    media_files = []
    test_files_path = Path(__file__).parent / "test_files.txt"

    if not test_files_path.exists():
        print(f"Warning: Test file list not found: {test_files_path}")
        return []

    with open(test_files_path) as f:
        for line in f:
            # Remove comments and whitespace
            line = line.split('#')[0].strip()
            if not line:
                continue

            # Handle paths relative to TEST_VECTORS_DIR
            path = Path(line)
            if not path.is_absolute():
                path = TEST_VECTORS_DIR / path
                
            if path.exists():
                media_files.append(path)
            else:
                raise FileNotFoundError(f"Test file not found: {line} (looked in {path})")

    return media_files
