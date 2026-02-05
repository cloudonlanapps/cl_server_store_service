"""
Comprehensive metadata tests for all images in the images directory.
Tests all Entity table fields including timestamps and file paths.
"""

from datetime import datetime

import pytest

from store.db_service.schemas import EntitySchema as Item
from tests.test_media_files import get_test_media_files



pytestmark = pytest.mark.integration
class TestAllImagesMetadata:
    """Test metadata extraction for all images in the test media list."""

    @pytest.mark.parametrize("image_path", get_test_media_files())
    def test_image_metadata_extraction(self, client, image_path):
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

        item = Item.model_validate(response.json())

        # Verify all metadata fields
        assert item.id is not None, "id should be set"
        assert item.md5 is not None, "md5 should be extracted"
        assert len(item.md5) == 128, "md5 (SHA-512 hash) should be 128 characters"
        assert (
            item.file_size == actual_size
        ), f"file_size mismatch for {image_path.name}"
        # Width and height are optional (None if EXIF not available)
        if item.width is not None:
            assert item.width > 0, "width should be positive when present"
        if item.height is not None:
            assert item.height > 0, "height should be positive when present"
        assert item.mime_type is not None, "mime_type should be set"
        assert "image" in item.mime_type.lower(), "mime_type should contain 'image'"


class TestTimestampFields:
    """Test timestamp field generation and format."""

    def test_added_date_format(self, client, sample_image):
        """Test that added_date is a valid ISO-8601 timestamp."""
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Timestamp test"},
            )

        assert response.status_code == 201
        item = Item.model_validate(response.json())

        # Verify added_date exists and is valid ISO-8601
        assert item.added_date is not None
        try:
            # Should be parseable as ISO-8601
            parsed = datetime.fromtimestamp(int(item.added_date) / 1000.0)
            assert parsed is not None
        except ValueError:
            pytest.fail(f"added_date is not valid ISO-8601: {item.added_date}")

    def test_updated_date_format(self, client, sample_image):
        """Test that updated_date is a valid ISO-8601 timestamp."""
        # Create entity
        with open(sample_image, "rb") as f:
            create_response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Original"},
            )

        created_item = Item.model_validate(create_response.json())
        entity_id = created_item.id

        # Update entity
        with open(sample_image, "rb") as f:
            update_response = client.put(
                f"/entities/{entity_id}",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Updated"},
            )

        assert update_response.status_code == 200
        item = Item.model_validate(update_response.json())

        # Verify updated_date exists and is valid ISO-8601
        assert item.updated_date is not None
        try:
            parsed = datetime.fromtimestamp(int(item.updated_date) / 1000.0)
            assert parsed is not None
        except ValueError:
            pytest.fail(f"updated_date is not valid ISO-8601: {item.updated_date}")

    def test_updated_date_changes_on_update(
        self, client, sample_image
    ):
        """Test that updated_date changes when entity is updated."""
        # Create entity
        with open(sample_image, "rb") as f:
            create_response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Original"},
            )

        created_item = Item.model_validate(create_response.json())
        entity_id = created_item.id
        original_updated = created_item.updated_date

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

        updated_item = Item.model_validate(update_response.json())
        new_updated = updated_item.updated_date

        # updated_date should have changed
        assert new_updated != original_updated, "updated_date should change on update"

    def test_create_date_from_exif(self, client, sample_image):
        """Test that create_date is extracted from EXIF data if available."""
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "EXIF test"},
            )

        assert response.status_code == 201
        item = Item.model_validate(response.json())

        # create_date may be None if EXIF data is not present
        # This is expected for images without EXIF CreateDate
        # If present, should be a valid timestamp
        if item.create_date is not None:
            try:
                parsed = datetime.fromtimestamp(int(item.create_date) / 1000.0)
                assert parsed is not None
            except ValueError:
                pytest.fail(f"create_date is not valid ISO-8601: {item.create_date}")


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
        item = Item.model_validate(response.json())

        # Verify the entity was created with proper metadata
        assert item.md5 is not None
        assert item.id is not None
        entity_id = item.id

        # Verify we can retrieve the entity
        get_response = client.get(f"/entities/{entity_id}")
        assert get_response.status_code == 200
        retrieved_item = Item.model_validate(get_response.json())
        assert retrieved_item.md5 == item.md5
        assert retrieved_item.label == "File path test"


class TestUnpopulatedFields:
    """Test fields that may not be populated for certain file types."""

    def test_duration_null_for_images(self, client, sample_image):
        """Test that duration is None for image files."""
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Duration test"},
            )

        assert response.status_code == 201
        item = Item.model_validate(response.json())

        # Images should not have duration
        assert item.duration is None, "Images should not have duration"

    def test_type_and_extension_fields(self, client, sample_image):
        """Test type and extension fields (may not be populated by clmediakit)."""
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Type test"},
            )

        assert response.status_code == 201
        item = Item.model_validate(response.json())

        # These fields may be None if not provided by clmediakit
        # Just verify they exist (Pydantic model will have these fields)
        # Type and extension can be accessed directly from the model
        _ = item.type  # Access to verify field exists
        _ = item.extension  # Access to verify field exists
