"""
Tests for entity validation rules.
"""

import pytest


class TestEntityValidation:
    """Test validation rules for entity creation and updates."""
    
    def test_create_non_collection_without_image_fails(self, client):
        """Test that creating a non-collection without an image fails."""
        response = client.post(
            "/entity/",
            data={
                "is_collection": "false",
                "label": "Non-collection without image"
            }
        )
        
        # Should fail because image is required for non-collections
        assert response.status_code in [400, 422, 500]  # Validation error
    
    def test_create_collection_without_image_succeeds(self, client):
        """Test that creating a collection without an image succeeds."""
        response = client.post(
            "/entity/",
            data={
                "is_collection": "true",
                "label": "Collection without image",
                "description": "This is a collection"
            }
        )
        
        # Should succeed because collections don't need images
        assert response.status_code == 201
        data = response.json()
        assert data["is_collection"] is True
        assert data["label"] == "Collection without image"
        assert data["md5"] is None  # No file uploaded
    
    def test_create_collection_with_image_fails(self, client, sample_image):
        """Test that creating a collection with an image fails."""
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entity/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={
                    "is_collection": "true",
                    "label": "Collection with image"
                }
            )
        
        # Should fail because collections should not have images
        assert response.status_code in [400, 422, 500]  # Validation error
    
    def test_update_collection_with_image_fails(self, client, sample_image):
        """Test that updating a collection with an image fails."""
        # Create a collection
        create_response = client.post(
            "/entity/",
            data={
                "is_collection": "true",
                "label": "Test Collection"
            }
        )
        
        assert create_response.status_code == 201
        entity_id = create_response.json()["id"]
        
        # Try to update with an image (should fail)
        with open(sample_image, "rb") as f:
            update_response = client.put(
                f"/entity/{entity_id}",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={
                    "is_collection": "true",
                    "label": "Updated Collection"
                }
            )
        
        # Should fail because collections should not have images
        assert update_response.status_code in [400, 422, 500]  # Validation error
    
    def test_cannot_change_is_collection_flag(self, client, sample_image):
        """Test that is_collection cannot be changed after creation."""
        # Create a non-collection
        with open(sample_image, "rb") as f:
            create_response = client.post(
                "/entity/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={
                    "is_collection": "false",
                    "label": "Non-collection"
                }
            )
        
        assert create_response.status_code == 201
        entity_id = create_response.json()["id"]
        
        # Try to change to collection (should fail)
        update_response = client.put(
            f"/entity/{entity_id}",
            data={
                "is_collection": "true",  # Trying to change
                "label": "Now a collection"
            }
        )
        
        # Should fail because is_collection is immutable
        assert update_response.status_code in [400, 422, 500]  # Validation error
    
    def test_update_non_collection_without_image_succeeds(self, client, sample_image):
        """Test that updating a non-collection without an image succeeds (image is optional for PUT)."""
        # Create a non-collection with image
        with open(sample_image, "rb") as f:
            create_response = client.post(
                "/entity/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={
                    "is_collection": "false",
                    "label": "Original"
                }
            )
        
        assert create_response.status_code == 201
        entity_id = create_response.json()["id"]
        original_md5 = create_response.json()["md5"]
        
        # Update without image (should succeed)
        update_response = client.put(
            f"/entity/{entity_id}",
            data={
                "is_collection": "false",
                "label": "Updated Label",
                "description": "Updated without changing file"
            }
        )
        
        # Should succeed - image is optional for PUT
        assert update_response.status_code == 200
        data = update_response.json()
        assert data["label"] == "Updated Label"
        assert data["description"] == "Updated without changing file"
        # MD5 should remain the same (file not changed)
        assert data["md5"] == original_md5
