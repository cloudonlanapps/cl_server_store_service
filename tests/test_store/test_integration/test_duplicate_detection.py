"""
Tests for duplicate file detection based on MD5 hash.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from store.db_service.schemas import EntitySchema as Item


class TestDuplicateDetection:
    """Test MD5-based duplicate detection. Returns existing data, and rejects new upload"""

    def test_duplicate_md5_returns_existing_entity(
        self, client: TestClient, sample_image: Path
    ) -> None:
        """Test that uploading the same file twice returns the existing entity data."""
        # First upload - should succeed
        with open(sample_image, "rb") as f:
            response1 = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "First upload"},
            )

        assert response1.status_code == 201
        item1 = Item.model_validate(response1.json())
        assert item1.md5 is not None
        assert item1.id is not None

        # Second upload of same file - should return existing entity
        with open(sample_image, "rb") as f:
            response2 = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Duplicate upload"},
            )

        # Duplicate POST returns 200 OK and existing entity
        assert response2.status_code == 200
        item2 = Item.model_validate(response2.json())
        assert item1 == item2

    def test_update_entity_with_duplicate_md5(
        self, client: TestClient, sample_images: list[Path]
    ) -> None:
        """Test that different files can be uploaded."""
        uploaded_md5s: list[str] = []

        for image_path in sample_images:
            with open(image_path, "rb") as f:
                response = client.post(
                    "/entities/",
                    files={"image": (image_path.name, f, "image/jpeg")},
                    data={
                        "is_collection": "false",
                        "label": f"Upload {image_path.name}",
                    },
                )

            assert response.status_code == 201
            item = Item.model_validate(response.json())
            assert item.md5 is not None
            uploaded_md5s.append(item.md5)

        # All MD5 hashes should be unique
        assert len(uploaded_md5s) == len(set(uploaded_md5s))

    def test_put_with_duplicate_file_rejected(
        self, client: TestClient, sample_images: list[Path]
    ) -> None:
        """Test that PUT with a file that already exists is rejected."""
        if len(sample_images) < 2:
            pytest.skip("Need at least 2 images for this test")

        image1, image2 = sample_images[0], sample_images[1]

        # Upload first image
        with open(image1, "rb") as f:
            response1 = client.post(
                "/entities/",
                files={"image": (image1.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "First"},
            )
        assert response1.status_code == 201
        item1 = Item.model_validate(response1.json())
        assert item1.id is not None
        entity1_id = item1.id

        # Upload second image
        with open(image2, "rb") as f:
            response2 = client.post(
                "/entities/",
                files={"image": (image2.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Second"},
            )
        assert response2.status_code == 201
        item2 = Item.model_validate(response2.json())
        assert item2.id is not None
        assert item2.md5 is not None

        # Try to update entity1 with image2 (should be rejected)
        with open(image2, "rb") as f:
            response3 = client.put(
                f"/entities/{entity1_id}",
                files={"image": (image2.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Updated"},
            )

        assert response3.status_code == 409
        # item3 = Item.model_validate(response3.json())
        # assert item3 == item2

    def test_put_same_entity_with_same_file_allowed(
        self, client: TestClient, sample_image: Path
    ) -> None:
        """Test that updating an entity with its own file is allowed."""
        # Upload image
        with open(sample_image, "rb") as f:
            response1 = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Original"},
            )

        assert response1.status_code == 201
        item1 = Item.model_validate(response1.json())
        assert item1.id is not None
        assert item1.md5 is not None
        entity_id = item1.id
        original_md5 = item1.md5

        # Update same entity with same file (should succeed)
        with open(sample_image, "rb") as f:
            response2 = client.put(
                f"/entities/{entity_id}",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Updated"},
            )

        assert response2.status_code == 200
        item2 = Item.model_validate(response2.json())
        assert item2.md5 == original_md5
        assert item2.label == "Updated"
