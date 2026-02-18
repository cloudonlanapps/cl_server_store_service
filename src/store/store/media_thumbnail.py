from __future__ import annotations

import os
from pathlib import Path

from cl_ml_tools.plugins.media_thumbnail.algo.image_thumbnail import image_thumbnail
from cl_ml_tools.plugins.media_thumbnail.algo.video_thumbnail import video_thumbnail
from loguru import logger

from store.db_service import EntitySchema


class ThumbnailGenerator:
    """Helper class to generate thumbnails for media entities."""

    @staticmethod
    def get_thumbnail_path(file_path: str) -> str:
        """Get the expected thumbnail path for a given file path."""
        # Convention: <filename>.<ext> -> <filename>.tb.png (or .tn.jpeg based on routes.py?)
        # Wait, routes.py said: assumptions .tn.jpeg convention from media_repo
        # Let's check routes.py again.
        # Line 624: preview_path = f"{media_path}.tn.jpeg"
        # The user request said: <filename>.<ext> --> <filename>.tb.png
        # BUT routes.py currently looks for .tn.jpeg.
        # If I change it to .tb.png, I must update routes.py too.
        # User REQ: "thumbnail is placed in the same folder in with the name <filename>.<ext> --> <filename>.tb.png."
        # I should follow the user request and update routes.py to look for .tb.png (or both?)
        # Let's stick to the User Request: .tb.png
        return f"{file_path}.tb.png"

    @staticmethod
    def generate(file_path: str, mime_type: str | None) -> str | None:
        """
        Generate a thumbnail for the given file if it's a supported media type.

        Args:
            file_path: Absolute path to the source file.
            mime_type: MIME type of the file.

        Returns:
            Path to the generated thumbnail, or None if not generated.
        """
        if not mime_type or not os.path.exists(file_path):
            return None

        output_path = ThumbnailGenerator.get_thumbnail_path(file_path)
        
        try:
            if mime_type.startswith("image/"):
                # Use image_thumbnail
                # It returns the output path as string
                result = image_thumbnail(
                    input_path=file_path,
                    output_path=output_path,
                    width=256, # Default size
                    maintain_aspect_ratio=True
                )
                logger.info(f"Generated image thumbnail: {result}")
                return result

            elif mime_type.startswith("video/"):
                # Use video_thumbnail
                result = video_thumbnail(
                    input_path=file_path,
                    output_path=output_path,
                    width=256
                )
                logger.info(f"Generated video thumbnail: {result}")
                return result
            
        except Exception as e:
            logger.error(f"Failed to generate thumbnail for {file_path}: {e}")
            # We don't raise here to avoid blocking the main operation? 
            # Or should we? The plan implies synchronous generation.
            # If it fails, maybe we just log it. The file is still saved.
            return None

        return None

    @staticmethod
    def delete(file_path: str) -> bool:
        """
        Delete the thumbnail associated with the file path.
        
        Args:
            file_path: Absolute path to the source file.
            
        Returns:
            True if deleted, False if not found or failed.
        """
        thumb_path = ThumbnailGenerator.get_thumbnail_path(file_path)
        try:
            if os.path.exists(thumb_path):
                os.remove(thumb_path)
                logger.info(f"Deleted thumbnail: {thumb_path}")
                return True
        except Exception as e:
            logger.warning(f"Failed to delete thumbnail {thumb_path}: {e}")
        return False
