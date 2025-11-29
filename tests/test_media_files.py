"""
Test image file paths loader.

Loads test image/video file paths from test_files.txt.
"""

from pathlib import Path

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
        
    with open(test_files_path, "r") as f:
        for line in f:
            # Remove comments and whitespace
            line = line.split('#')[0].strip()
            if not line:
                continue
            
            # Handle paths relative to project root
            # If the path in text file is relative (e.g. "images/foo.jpg"), 
            # we assume it's relative to the project root (where pytest is run).
            path = Path(line)
            if path.exists():
                media_files.append(path)
            else:
                print(f"Warning: Test file not found: {line}")
    
    return media_files
