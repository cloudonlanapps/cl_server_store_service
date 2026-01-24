"""Media metadata extraction module using cl_ml_tools.algorithms.

This module provides metadata extraction for media files (images, videos, audio)
using ExifTool, ffprobe, and perceptual hashing algorithms.
"""

from __future__ import annotations

import subprocess
import tempfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
import magic

from cl_ml_tools.algorithms import (
    MediaType,
    MetadataExtractor,
    determine_mime,
    get_md5_hexdigest,
    sha512hash_image,
    sha512hash_video2,
)
from loguru import logger
from pydantic import BaseModel, Field


class FFProbeFormat(BaseModel):
    """FFProbe format section from JSON output."""

    duration: str | float | int | None = None


class FFProbeOutput(BaseModel):
    """FFProbe JSON output structure."""

    format: FFProbeFormat | None = None


class MediaMetadata(BaseModel):
    """Media metadata extracted from a file.

    Attributes:
        file_size: File size in bytes
        md5: Hash value (SHA-512 for images/videos, MD5 for others)
        extension: File extension without dot (e.g., "jpg")
        mime_type: MIME type string (e.g., "image/jpeg")
        type: Media type classification (e.g., "image", "video")
        width: Image/video width in pixels (None if not available)
        height: Image/video height in pixels (None if not available)
        duration: Video/audio duration in seconds (None if not available)
        create_date: Creation timestamp in milliseconds since epoch (None if not available)
    """

    file_size: int = Field(..., description="File size in bytes", ge=0)
    md5: str = Field(..., description="File hash (SHA-512 or MD5)", min_length=32)
    extension: str = Field(..., description="File extension without dot", min_length=1)
    mime_type: str = Field(..., description="MIME type", min_length=1)
    type: str = Field(..., description="Media type classification", min_length=1)
    width: int | None = Field(None, description="Width in pixels", ge=0)
    height: int | None = Field(None, description="Height in pixels", ge=0)
    duration: float | None = Field(None, description="Duration in seconds", ge=0)
    create_date: int | None = Field(
        None, description="Creation timestamp in milliseconds since epoch"
    )


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
            + "Install with: brew install exiftool (macOS) or "
            + "apt-get install libimage-exiftool-perl (Linux)"
        )

    # Check ffprobe
    try:
        _ = subprocess.run(
            ["ffprobe", "-version"], capture_output=True, check=True, timeout=5
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise RuntimeError(
            "ffprobe not installed. "
            + "Install with: brew install ffmpeg (macOS) or "
            + "apt-get install ffmpeg (Linux)"
        ) from e


class MediaMetadataExtractor:
    """Extracts metadata from media files using various tools."""

    def __init__(self) -> None:
        """Initialize the metadata extractor."""
        self.exif_extractor: MetadataExtractor = MetadataExtractor()

    def extract_metadata(self, file_bytes: bytes, filename: str) -> MediaMetadata:
        """Extract comprehensive metadata from a media file.

        Args:
            file_bytes: File content as bytes
            filename: Original filename (used for temp file creation)

        Returns:
            MediaMetadata instance containing all extracted metadata fields

        Raises:
            ValueError: If MIME type or extension cannot be determined
            RuntimeError: If hash computation fails
        """

        # Step 1: Determine MIME type and media type
        bytes_io = BytesIO(file_bytes)
        try:
            media_type = determine_mime(bytes_io)
        except Exception as e:
            raise ValueError(f"Failed to determine MIME type: {e}") from e

        # Get MIME type string using python-magic
        mime = magic.Magic(mime=True)
        mime_type_str = mime.from_buffer(file_bytes)
        if not mime_type_str:
            mime_type_str = "application/octet-stream"

        # Step 2: Extract extension from MIME type
        try:
            extension = self._determine_extension(mime_type_str, media_type)
        except ValueError as e:
            raise ValueError(f"Cannot determine extension: {e}") from e

        # Step 3: Set file size
        file_size = len(file_bytes)

        # Step 4: Compute hash based on media type
        try:
            file_hash = self._compute_hash(file_bytes, media_type)
        except Exception as e:
            raise RuntimeError(f"Hash computation failed: {e}") from e

        # Step 5: Extract EXIF metadata using ExifTool
        # Create temporary file for ExifTool processing
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=Path(filename).suffix
        ) as tmp_file:
            _ = tmp_file.write(file_bytes)
            tmp_path = tmp_file.name

        try:
            exif_data = self.exif_extractor.extract_metadata_all(tmp_path)

            # Extract width (try multiple possible fields)
            width_val = (
                exif_data.get("File:ImageWidth")
                or exif_data.get("EXIF:ImageWidth")
                or exif_data.get("Composite:ImageWidth")
                or exif_data.get("EXIF:ExifImageWidth")
            )
            # Type guard: only convert if it's int, float, or str (not dict/list)
            if width_val is not None and isinstance(width_val, (int, float, str)):
                width = int(width_val)
            else:
                width = None

            # Extract height (try multiple possible fields)
            height_val = (
                exif_data.get("File:ImageHeight")
                or exif_data.get("EXIF:ImageHeight")
                or exif_data.get("Composite:ImageHeight")
                or exif_data.get("EXIF:ExifImageHeight")
            )
            # Type guard: only convert if it's int, float, or str (not dict/list)
            if height_val is not None and isinstance(height_val, (int, float, str)):
                height = int(height_val)
            else:
                height = None

            # Extract Duration from EXIF (for videos)
            duration_val = (
                exif_data.get("QuickTime:Duration")
                or exif_data.get("File:Duration")
                or exif_data.get("Composite:Duration")
            )
            # Type guard: only convert if it's int, float, or str (not dict/list)
            if duration_val is not None and isinstance(duration_val, (int, float, str)):
                duration = float(duration_val)
            else:
                duration = None

            # Extract CreateDate from EXIF
            create_date_str = (
                exif_data.get("EXIF:DateTimeOriginal")
                or exif_data.get("EXIF:CreateDate")
                or exif_data.get("EXIF:DateTime")
                or exif_data.get("QuickTime:CreateDate")
            )
            create_date_ms: int | None = None

        except Exception as e:
            logger.warning(f"EXIF extraction failed for {filename}: {e}")
            # Set graceful None values for optional fields
            width = None
            height = None
            duration = None
            create_date_str = None
            create_date_ms = None
        finally:
            # Clean up temporary file
            Path(tmp_path).unlink(missing_ok=True)

        # Step 6: Video duration fallback using ffprobe
        if media_type == MediaType.VIDEO and duration is None:
            try:
                duration_fallback = self._extract_video_duration(file_bytes, filename)
                if duration_fallback is not None:
                    duration = duration_fallback
            except Exception as e:
                logger.warning(
                    f"ffprobe duration extraction failed for {filename}: {e}"
                )

        # Step 7: Convert CreateDate to milliseconds timestamp
        if create_date_str and isinstance(create_date_str, str):
            try:
                # Parse EXIF date format: YYYY:MM:DD HH:MM:SS
                dt = datetime.strptime(create_date_str, "%Y:%m:%d %H:%M:%S")
                create_date_ms = int(dt.timestamp() * 1000)
            except ValueError:
                # Failed to parse, set to None
                logger.warning(f"Could not parse CreateDate: {create_date_str}")
                create_date_ms = None

        # Return Pydantic model
        return MediaMetadata(
            file_size=file_size,
            md5=file_hash,
            extension=extension,
            mime_type=mime_type_str,
            type=media_type.value,
            width=width,
            height=height,
            duration=duration,
            create_date=create_date_ms,
        )

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
                # Ensure it's a string (sha512hash_image returns tuple[str, int])
                return str(file_hash)
            elif media_type == MediaType.VIDEO:
                # Perceptual hash for videos
                file_hash, _ = sha512hash_video2(bytes_io)
                # Ensure it's a string (sha512hash_video2 returns tuple[str, int])
                return str(file_hash)
            else:
                # MD5 for other files
                return get_md5_hexdigest(bytes_io)
        except Exception as e:
            raise RuntimeError(f"Hash computation failed: {e}") from e

    def _extract_video_duration(self, file_bytes: bytes, filename: str) -> float | None:
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
            _ = tmp_file.write(file_bytes)
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
                # Parse ffprobe JSON output using Pydantic for type safety
                try:
                    ffprobe_data = FFProbeOutput.model_validate_json(result.stdout)
                    if ffprobe_data.format and ffprobe_data.format.duration is not None:
                        return float(ffprobe_data.format.duration)
                except Exception:
                    # Validation failed - malformed JSON or unexpected structure
                    return None

        except subprocess.TimeoutExpired:
            logger.warning(f"ffprobe timeout for {filename}")
        except Exception as e:
            logger.warning(f"ffprobe execution failed for {filename}: {e}")
        finally:
            # Clean up temporary file
            Path(tmp_path).unlink(missing_ok=True)

        return None
