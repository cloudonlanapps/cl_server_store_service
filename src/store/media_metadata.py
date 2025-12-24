"""Media metadata extraction module using cl_ml_tools.algorithms.

This module provides metadata extraction for media files (images, videos, audio)
using ExifTool, ffprobe, and perceptual hashing algorithms.
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from cl_ml_tools.algorithms import (
    MediaType,
    MetadataExtractor,
    determine_mime,
    get_md5_hexdigest,
    sha512hash_image,
    sha512hash_video2,
)

logger = logging.getLogger(__name__)


def validate_tools() -> None:
    """Validate required tools are available.

    Checks that ExifTool and ffprobe are installed and accessible.

    Raises:
        RuntimeError: If ExifTool or ffprobe is not available
    """
    # Check ExifTool
    extractor = MetadataExtractor()
    if not extractor.is_exiftool_available():
        raise RuntimeError(
            "ExifTool not installed. "
            "Install with: brew install exiftool (macOS) or "
            "apt-get install libimage-exiftool-perl (Linux)"
        )

    # Check ffprobe
    try:
        subprocess.run(
            ["ffprobe", "-version"],
            capture_output=True,
            check=True,
            timeout=5
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise RuntimeError(
            "ffprobe not installed. "
            "Install with: brew install ffmpeg (macOS) or "
            "apt-get install ffmpeg (Linux)"
        ) from e


class MediaMetadataExtractor:
    """Extracts metadata from media files using various tools."""

    def __init__(self) -> None:
        """Initialize the metadata extractor."""
        self.exif_extractor = MetadataExtractor()

    def extract_metadata(
        self, file_bytes: bytes, filename: str
    ) -> dict[str, str | int | float | None]:
        """Extract comprehensive metadata from a media file.

        Args:
            file_bytes: File content as bytes
            filename: Original filename (used for temp file creation)

        Returns:
            Dictionary containing metadata fields:
                - FileSize: int - File size in bytes
                - md5: str - Hash (perceptual for images/videos, MD5 for others)
                - extension: str - File extension
                - MIMEType: str - MIME type string
                - type: str - Media type classification
                - ImageWidth: int | None - Width in pixels
                - ImageHeight: int | None - Height in pixels
                - Duration: float | None - Duration in seconds (videos only)
                - CreateDate: int | None - Creation date in milliseconds since epoch

        Raises:
            ValueError: If MIME type or extension cannot be determined
            RuntimeError: If hash computation fails
        """
        metadata: dict[str, str | int | float | None] = {}

        # Step 1: Determine MIME type and media type
        bytes_io = BytesIO(file_bytes)
        try:
            media_type = determine_mime(bytes_io)
        except Exception as e:
            raise ValueError(f"Failed to determine MIME type: {e}") from e

        # Get MIME type string using python-magic
        import magic
        mime = magic.Magic(mime=True)
        mime_type_str = mime.from_buffer(file_bytes)
        if not mime_type_str:
            mime_type_str = "application/octet-stream"

        metadata["MIMEType"] = mime_type_str
        metadata["type"] = media_type.value

        # Step 2: Extract extension from MIME type
        try:
            extension = self._determine_extension(mime_type_str, media_type)
            metadata["extension"] = extension
        except ValueError as e:
            raise ValueError(f"Cannot determine extension: {e}") from e

        # Step 3: Set file size
        metadata["FileSize"] = len(file_bytes)

        # Step 4: Compute hash based on media type
        try:
            file_hash = self._compute_hash(file_bytes, media_type)
            metadata["md5"] = file_hash
        except Exception as e:
            raise RuntimeError(f"Hash computation failed: {e}") from e

        # Step 5: Extract EXIF metadata using ExifTool
        # Create temporary file for ExifTool processing
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=Path(filename).suffix
        ) as tmp_file:
            tmp_file.write(file_bytes)
            tmp_path = tmp_file.name

        try:
            exif_data = self.exif_extractor.extract_metadata_all(tmp_path)

            # Extract width (try multiple possible fields)
            width = (
                exif_data.get("File:ImageWidth")
                or exif_data.get("EXIF:ImageWidth")
                or exif_data.get("Composite:ImageWidth")
                or exif_data.get("EXIF:ExifImageWidth")
            )
            if width is not None:
                metadata["ImageWidth"] = int(width)
            else:
                metadata["ImageWidth"] = None

            # Extract height (try multiple possible fields)
            height = (
                exif_data.get("File:ImageHeight")
                or exif_data.get("EXIF:ImageHeight")
                or exif_data.get("Composite:ImageHeight")
                or exif_data.get("EXIF:ExifImageHeight")
            )
            if height is not None:
                metadata["ImageHeight"] = int(height)
            else:
                metadata["ImageHeight"] = None

            # Extract Duration from EXIF (for videos)
            duration = (
                exif_data.get("QuickTime:Duration")
                or exif_data.get("File:Duration")
                or exif_data.get("Composite:Duration")
            )
            if duration is not None:
                metadata["Duration"] = float(duration)
            else:
                metadata["Duration"] = None

            # Extract CreateDate from EXIF
            create_date = (
                exif_data.get("EXIF:DateTimeOriginal")
                or exif_data.get("EXIF:CreateDate")
                or exif_data.get("EXIF:DateTime")
                or exif_data.get("QuickTime:CreateDate")
            )
            if create_date:
                metadata["CreateDate"] = create_date
            else:
                metadata["CreateDate"] = None

        except Exception as e:
            logger.warning(f"EXIF extraction failed for {filename}: {e}")
            # Set graceful None values for optional fields
            metadata["ImageWidth"] = None
            metadata["ImageHeight"] = None
            metadata["Duration"] = None
            metadata["CreateDate"] = None
        finally:
            # Clean up temporary file
            Path(tmp_path).unlink(missing_ok=True)

        # Step 6: Video duration fallback using ffprobe
        if media_type == MediaType.VIDEO and metadata.get("Duration") is None:
            try:
                duration_fallback = self._extract_video_duration(file_bytes, filename)
                if duration_fallback is not None:
                    metadata["Duration"] = duration_fallback
            except Exception as e:
                logger.warning(f"ffprobe duration extraction failed for {filename}: {e}")

        # Step 7: Convert CreateDate to milliseconds timestamp
        create_date_val = metadata.get("CreateDate")
        if create_date_val and isinstance(create_date_val, str):
            try:
                # Parse EXIF date format: YYYY:MM:DD HH:MM:SS
                dt = datetime.strptime(create_date_val, "%Y:%m:%d %H:%M:%S")
                metadata["CreateDate"] = int(dt.timestamp() * 1000)
            except ValueError:
                # Failed to parse, set to None
                logger.warning(f"Could not parse CreateDate: {create_date_val}")
                metadata["CreateDate"] = None

        return metadata

    def _determine_extension(self, mime_type: str, media_type: MediaType) -> str:
        """Determine file extension from MIME type.

        Args:
            mime_type: MIME type string (e.g., "image/jpeg")
            media_type: MediaType enum value

        Returns:
            File extension without dot (e.g., "jpg")

        Raises:
            ValueError: If extension cannot be determined
        """
        # Common MIME type to extension mappings
        mime_to_ext: dict[str, str] = {
            # Images
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/gif": "gif",
            "image/webp": "webp",
            "image/bmp": "bmp",
            "image/tiff": "tiff",
            "image/svg+xml": "svg",
            "image/heic": "heic",
            "image/heif": "heif",
            # Videos
            "video/mp4": "mp4",
            "video/mpeg": "mpeg",
            "video/quicktime": "mov",
            "video/x-msvideo": "avi",
            "video/x-matroska": "mkv",
            "video/webm": "webm",
            "video/3gpp": "3gp",
            # Audio
            "audio/mpeg": "mp3",
            "audio/wav": "wav",
            "audio/ogg": "ogg",
            "audio/flac": "flac",
            "audio/aac": "aac",
            # Documents
            "application/pdf": "pdf",
            "text/plain": "txt",
        }

        if mime_type in mime_to_ext:
            return mime_to_ext[mime_type]

        # Try to extract from mime_type pattern (e.g., "image/jpeg" → "jpeg")
        if "/" in mime_type:
            subtype = mime_type.split("/")[1]
            # Remove any parameters (e.g., "jpeg; charset=utf-8" → "jpeg")
            subtype = subtype.split(";")[0].strip()
            if subtype:
                return subtype

        # Fallback based on media type
        if media_type == MediaType.IMAGE:
            return "jpg"
        elif media_type == MediaType.VIDEO:
            return "mp4"
        elif media_type == MediaType.AUDIO:
            return "mp3"
        elif media_type == MediaType.TEXT:
            return "txt"
        else:
            return "bin"

    def _compute_hash(self, file_bytes: bytes, media_type: MediaType) -> str:
        """Compute hash based on media type.

        Uses perceptual hashing for images and videos, MD5 for other files.

        Args:
            file_bytes: File content as bytes
            media_type: MediaType enum value

        Returns:
            Hash string (hex digest)

        Raises:
            RuntimeError: If hash computation fails
        """
        bytes_io = BytesIO(file_bytes)

        try:
            if media_type == MediaType.IMAGE:
                # Perceptual hash for images
                file_hash, _ = sha512hash_image(bytes_io)
                return file_hash
            elif media_type == MediaType.VIDEO:
                # Perceptual hash for videos
                file_hash, _ = sha512hash_video2(bytes_io)
                return file_hash
            else:
                # MD5 for other files
                return get_md5_hexdigest(bytes_io)
        except Exception as e:
            raise RuntimeError(f"Hash computation failed: {e}") from e

    def _extract_video_duration(
        self, file_bytes: bytes, filename: str
    ) -> float | None:
        """Extract video duration using ffprobe.

        Args:
            file_bytes: Video file content as bytes
            filename: Original filename for extension

        Returns:
            Duration in seconds as float, or None if extraction fails
        """
        # Create temporary file for ffprobe
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=Path(filename).suffix
        ) as tmp_file:
            tmp_file.write(file_bytes)
            tmp_path = tmp_file.name

        try:
            # Run ffprobe to get duration
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "json",
                    tmp_path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                data: dict[str, Any] = json.loads(result.stdout)
                duration_str = data.get("format", {}).get("duration")
                if duration_str:
                    return float(duration_str)

        except subprocess.TimeoutExpired:
            logger.warning(f"ffprobe timeout for {filename}")
        except Exception as e:
            logger.warning(f"ffprobe execution failed for {filename}: {e}")
        finally:
            # Clean up temporary file
            Path(tmp_path).unlink(missing_ok=True)

        return None
