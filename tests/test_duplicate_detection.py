"""
Tests for duplicate file detection based on MD5 hash.
"""

import pytest


class TestDuplicateDetection:
    """Test MD5-based duplicate detection. Returns existing data, and rejects new upload"""

    def test_duplicate_upload_returns_existing_entity(self, client, sample_image, clean_media_dir):
        """Test that uploading the same file twice returns the existing entity data."""
        # First upload - should succeed
        with open(sample_image, "rb") as f:
            response1 = client.post(
                "/entity/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "First upload"},
            )

        assert response1.status_code == 201
        data1 = response1.json()
        md5_hash = data1["md5"]
        entity_id = data1["id"]

        # Second upload of same file - should return existing entity
        with open(sample_image, "rb") as f:
            response2 = client.post(
                "/entity/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Duplicate upload"},
            )

        assert response2.status_code == 201
        data = response2.json()
        assert data1 == data

    def test_different_files_allowed(self, client, sample_images, clean_media_dir):
        """Test that different files can be uploaded."""
        uploaded_md5s = []

        for image_path in sample_images:
            with open(image_path, "rb") as f:
                response = client.post(
                    "/entity/",
                    files={"image": (image_path.name, f, "image/jpeg")},
                    data={
                        "is_collection": "false",
                        "label": f"Upload {image_path.name}",
                    },
                )

            assert response.status_code == 201
            data = response.json()
            uploaded_md5s.append(data["md5"])

        # All MD5 hashes should be unique
        assert len(uploaded_md5s) == len(set(uploaded_md5s))

    def test_put_with_duplicate_file_rejected(
        self, client, sample_images, clean_media_dir
    ):
        """Test that PUT with a file that already exists is rejected."""
        if len(sample_images) < 2:
            pytest.skip("Need at least 2 images for this test")

        image1, image2 = sample_images[0], sample_images[1]

        # Upload first image
        with open(image1, "rb") as f:
            response1 = client.post(
                "/entity/",
                files={"image": (image1.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "First"},
            )
        assert response1.status_code == 201
        entity1_id = response1.json()["id"]
        data1 = response1.json()

        # Upload second image
        with open(image2, "rb") as f:
            response2 = client.post(
                "/entity/",
                files={"image": (image2.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Second"},
            )
        assert response2.status_code == 201
        entity2_id = response2.json()["id"]
        md5_2 = response2.json()["md5"]
        data2 = response2.json()

        # Try to update entity1 with image2 (should be rejected)
        with open(image2, "rb") as f:
            response3 = client.put(
                f"/entity/{entity1_id}",
                files={"image": (image2.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Updated"},
            )

        assert response3.status_code == 200
        data = response3.json()
        assert data == data2

    def test_put_same_entity_with_same_file_allowed(
        self, client, sample_image, clean_media_dir
    ):
        """Test that updating an entity with its own file is allowed."""
        # Upload image
        with open(sample_image, "rb") as f:
            response1 = client.post(
                "/entity/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Original"},
            )

        assert response1.status_code == 201
        entity_id = response1.json()["id"]
        original_md5 = response1.json()["md5"]

        # Update same entity with same file (should succeed)
        with open(sample_image, "rb") as f:
            response2 = client.put(
                f"/entity/{entity_id}",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Updated"},
            )

        assert response2.status_code == 200
        data = response2.json()
        assert data["md5"] == original_md5
        assert data["label"] == "Updated"
