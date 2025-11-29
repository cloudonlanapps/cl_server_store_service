"""
Tests for PUT endpoint with file replacement and metadata extraction.
"""

import pytest


class TestPutEndpoint:
    """Test PUT endpoint file replacement and metadata extraction."""
    
    def test_put_with_file_replacement(self, client, sample_images, clean_media_dir):
        """Test PUT endpoint replaces file and extracts new metadata."""
        if len(sample_images) < 2:
            pytest.skip("Need at least 2 images for this test")
        
        image1, image2 = sample_images[0], sample_images[1]
        
        # Create entity with first image
        with open(image1, "rb") as f:
            create_response = client.post(
                "/entity/",
                files={"image": (image1.name, f, "image/jpeg")},
                data={
                    "is_collection": "false",
                    "label": "Original",
                    "description": "First image"
                }
            )
        
        assert create_response.status_code == 201
        original_data = create_response.json()
        entity_id = original_data["id"]
        
        # Store original metadata
        original_md5 = original_data["md5"]
        original_width = original_data["width"]
        original_height = original_data["height"]
        original_size = original_data["file_size"]
        original_mime = original_data["mime_type"]
        
        # Update with second image
        with open(image2, "rb") as f:
            update_response = client.put(
                f"/entity/{entity_id}",
                files={"image": (image2.name, f, "image/jpeg")},
                data={
                    "is_collection": "false",
                    "label": "Updated",
                    "description": "Second image"
                }
            )
        
        assert update_response.status_code == 200
        updated_data = update_response.json()
        
        # Verify metadata was updated
        assert updated_data["id"] == entity_id
        assert updated_data["label"] == "Updated"
        assert updated_data["description"] == "Second image"
        
        # Verify NEW metadata was extracted
        assert updated_data["md5"] != original_md5
        assert updated_data["md5"] is not None
        assert updated_data["width"] is not None
        assert updated_data["height"] is not None
        assert updated_data["file_size"] is not None
        assert updated_data["mime_type"] is not None
        
        # Metadata should be different (different file)
        # Note: Only check if images are actually different sizes
        actual_size2 = image2.stat().st_size
        if actual_size2 != original_size:
            assert updated_data["file_size"] != original_size
    
    def test_put_metadata_accuracy(self, client, sample_images, clean_media_dir):
        """Test that PUT endpoint extracts accurate metadata."""
        if len(sample_images) < 2:
            pytest.skip("Need at least 2 images for this test")
        
        image1, image2 = sample_images[0], sample_images[1]
        actual_size2 = image2.stat().st_size
        
        # Create entity
        with open(image1, "rb") as f:
            create_response = client.post(
                "/entity/",
                files={"image": (image1.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Test"}
            )
        
        entity_id = create_response.json()["id"]
        
        # Update with second image
        with open(image2, "rb") as f:
            update_response = client.put(
                f"/entity/{entity_id}",
                files={"image": (image2.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Updated"}
            )
        
        assert update_response.status_code == 200
        data = update_response.json()
        
        # Verify accurate metadata extraction
        assert data["file_size"] == actual_size2
        assert data["width"] > 0
        assert data["height"] > 0
        assert "image" in data["mime_type"].lower()
        assert len(data["md5"]) == 32  # MD5 hash length
    
    def test_put_without_file_succeeds_for_non_collection(self, client, sample_image, clean_media_dir):
        """Test that PUT without file succeeds for non-collections (image is optional)."""
        # Create entity with image
        with open(sample_image, "rb") as f:
            create_response = client.post(
                "/entity/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Test"}
            )
        
        entity_id = create_response.json()["id"]
        
        # Update without file (should succeed - image is optional for PUT on non-collections)
        update_response = client.put(
            f"/entity/{entity_id}",
            data={
                "is_collection": "false",
                "label": "Updated without file"
            }
        )
        
        # Should succeed because image is optional for PUT operations on non-collections
        assert update_response.status_code == 200
        data = update_response.json()
        assert data["label"] == "Updated without file"
        # File metadata should remain from original upload
        assert data["md5"] is not None
    
    def test_put_updates_all_metadata_fields(self, client, sample_images, clean_media_dir):
        """Test that PUT updates all metadata fields correctly."""
        if len(sample_images) < 2:
            pytest.skip("Need at least 2 images for this test")
        
        image1, image2 = sample_images[0], sample_images[1]
        
        # Create entity
        with open(image1, "rb") as f:
            create_response = client.post(
                "/entity/",
                files={"image": (image1.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Original"}
            )
        
        entity_id = create_response.json()["id"]
        
        # Update with different image
        with open(image2, "rb") as f:
            update_response = client.put(
                f"/entity/{entity_id}",
                files={"image": (image2.name, f, "image/jpeg")},
                data={
                    "is_collection": "false",
                    "label": "Updated Label",
                    "description": "Updated Description",
                    "parent_id": "123"
                }
            )
        
        assert update_response.status_code == 200
        data = update_response.json()
        
        # Verify client-provided fields updated
        assert data["label"] == "Updated Label"
        assert data["description"] == "Updated Description"
        assert data["parent_id"] == 123
        
        # Verify all metadata fields are present and valid
        metadata_fields = ["md5", "width", "height", "file_size", "mime_type"]
        for field in metadata_fields:
            assert data[field] is not None, f"{field} should not be None"
        
        # Verify updated_date changed
        assert data["updated_date"] is not None
    
    def test_put_same_file_updates_metadata(self, client, sample_image, clean_media_dir):
        """Test that PUT with same file still updates metadata correctly."""
        # Create entity
        with open(sample_image, "rb") as f:
            create_response = client.post(
                "/entity/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Original"}
            )
        
        entity_id = create_response.json()["id"]
        original_md5 = create_response.json()["md5"]
        
        # Update with same file
        with open(sample_image, "rb") as f:
            update_response = client.put(
                f"/entity/{entity_id}",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Updated"}
            )
        
        assert update_response.status_code == 200
        data = update_response.json()
        
        # MD5 should be same (same file)
        assert data["md5"] == original_md5
        
        # But label should be updated
        assert data["label"] == "Updated"
        
        # Metadata should still be present and valid
        assert data["width"] is not None
        assert data["height"] is not None
        assert data["file_size"] is not None
        assert data["mime_type"] is not None
