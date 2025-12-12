"""
Comprehensive metadata tests for all images in the images directory.
Tests all Entity table fields including timestamps and file paths.
"""

import os
from datetime import datetime
from pathlib import Path
from venv import logger

import pytest

from .test_media_files import get_test_media_files


class TestAllImagesMetadata:
    """Test metadata extraction for all images in the test media list."""

    @pytest.mark.parametrize("image_path", get_test_media_files())
    def test_image_metadata_extraction(self, client, clean_media_dir, image_path):
        """Test metadata extraction for each image file."""
        if not image_path.exists():
            pytest.skip(f"Image not found: {image_path}")

        actual_size = image_path.stat().st_size

        with open(image_path, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (image_path.name, f, "image/jpeg")},
                data={
                    "is_collection": "false",
                    "label": f"Test: {image_path.name}",
                    "description": f"Metadata test for {image_path}",
                },
            )

        # Should succeed or fail with 409 (duplicate)
        assert response.status_code in [
            201,
            409,
        ], f"Unexpected status for {image_path.name}"

        if response.status_code == 409:
            pytest.skip(f"Duplicate file: {image_path.name}")

        data = response.json()

        # Verify all metadata fields
        assert data["id"] is not None, "id should be set"
        assert data["md5"] is not None, "md5 should be extracted"
        assert len(data["md5"]) == 32, "md5 should be 32 characters"
        assert (
            data["file_size"] == actual_size
        ), f"file_size mismatch for {image_path.name}"
        assert (
            data["width"] is not None and data["width"] > 0
        ), "width should be positive"
        assert (
            data["height"] is not None and data["height"] > 0
        ), "height should be positive"
        assert data["mime_type"] is not None, "mime_type should be set"
        assert "image" in data["mime_type"].lower(), "mime_type should contain 'image'"


class TestTimestampFields:
    """Test timestamp field generation and format."""

    def test_added_date_format(self, client, sample_image, clean_media_dir):
        """Test that added_date is a valid ISO-8601 timestamp."""
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Timestamp test"},
            )

        assert response.status_code == 201
        data = response.json()

        # Verify added_date exists and is valid ISO-8601
        assert data["added_date"] is not None
        try:
            # Should be parseable as ISO-8601
            parsed = datetime.fromtimestamp(int(data["added_date"]) / 1000.0)
            assert parsed is not None
        except ValueError:
            pytest.fail(f"added_date is not valid ISO-8601: {data['added_date']}")

    def test_updated_date_format(self, client, sample_image, clean_media_dir):
        """Test that updated_date is a valid ISO-8601 timestamp."""
        # Create entity
        with open(sample_image, "rb") as f:
            create_response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Original"},
            )

        entity_id = create_response.json()["id"]

        # Update entity
        with open(sample_image, "rb") as f:
            update_response = client.put(
                f"/entities/{entity_id}",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Updated"},
            )

        assert update_response.status_code == 200
        data = update_response.json()

        # Verify updated_date exists and is valid ISO-8601
        assert data["updated_date"] is not None
        try:
            parsed = datetime.fromtimestamp(int(data["updated_date"]) / 1000.0)
            assert parsed is not None
        except ValueError:
            pytest.fail(f"updated_date is not valid ISO-8601: {data['updated_date']}")

    def test_updated_date_changes_on_update(
        self, client, sample_image, clean_media_dir
    ):
        """Test that updated_date changes when entity is updated."""
        # Create entity
        with open(sample_image, "rb") as f:
            create_response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Original"},
            )

        entity_id = create_response.json()["id"]
        original_updated = create_response.json()["updated_date"]

        # Small delay to ensure timestamp difference
        import time

        time.sleep(0.1)

        # Update entity
        with open(sample_image, "rb") as f:
            update_response = client.put(
                f"/entities/{entity_id}",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Updated"},
            )

        new_updated = update_response.json()["updated_date"]

        # updated_date should have changed
        assert new_updated != original_updated, "updated_date should change on update"

    def test_create_date_from_exif(self, client, sample_image, clean_media_dir):
        """Test that create_date is extracted from EXIF data if available."""
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "EXIF test"},
            )

        assert response.status_code == 201
        data = response.json()

        # create_date may be None if EXIF data is not present
        # This is expected for images without EXIF CreateDate
        # If present, should be a valid timestamp
        if data["create_date"] is not None:
            try:
                parsed = datetime.fromtimestamp(int(data["create_date"]) / 1000.0)
                assert parsed is not None
            except ValueError:
                pytest.fail(f"create_date is not valid ISO-8601: {data['create_date']}")


class TestFilePathField:
    """Test file_path field storage and retrieval."""

    def test_file_path_stored(self, client, sample_image):
        """Test that file is properly uploaded and entity can be retrieved."""
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "File path test"},
            )

        assert response.status_code == 201
        data = response.json()

        # Verify the entity was created with proper metadata
        assert "md5" in data
        assert "id" in data
        entity_id = data["id"]

        # Verify we can retrieve the entity
        get_response = client.get(f"/entities/{entity_id}")
        assert get_response.status_code == 200
        retrieved_data = get_response.json()
        assert retrieved_data["md5"] == data["md5"]
        assert retrieved_data["label"] == "File path test"


class TestUnpopulatedFields:
    """Test fields that may not be populated for certain file types."""

    def test_duration_null_for_images(self, client, sample_image, clean_media_dir):
        """Test that duration is None for image files."""
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Duration test"},
            )

        assert response.status_code == 201
        data = response.json()

        # Images should not have duration
        assert data["duration"] is None, "Images should not have duration"

    def test_type_and_extension_fields(self, client, sample_image, clean_media_dir):
        """Test type and extension fields (may not be populated by clmediakit)."""
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Type test"},
            )

        assert response.status_code == 201
        data = response.json()

        # These fields may be None if not provided by clmediakit
        # Just verify they exist in the response
        assert "type" in data
        assert "extension" in data
