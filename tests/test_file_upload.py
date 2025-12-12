"""
Tests for file upload functionality with metadata extraction.
"""

import json
from pathlib import Path

import pytest


class TestFileUpload:
    """Test file upload with metadata extraction."""
    
    def test_upload_image_with_metadata(self, client, sample_image):
        """Test uploading an image and extracting metadata."""
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={
                    "is_collection": "false",
                    "label": f"Test: {sample_image.name}",
                    "description": "Test upload"
                }
            )

        assert response.status_code == 201
        data = response.json()

        # Verify entity was created
        assert data["id"] is not None
        assert data["label"] == f"Test: {sample_image.name}"
        assert data["is_collection"] is False

        # Verify metadata was extracted
        assert data["md5"] is not None
        assert data["width"] is not None
        assert data["height"] is not None
        assert data["file_size"] is not None
        assert data["mime_type"] is not None
        assert data["file_path"] is not None

        # Verify entity can be retrieved
        entity_id = data["id"]
        get_response = client.get(f"/entities/{entity_id}")
        assert get_response.status_code == 200
        assert get_response.json()["md5"] == data["md5"]
    
    def test_upload_multiple_images(self, client, sample_images):
        """Test uploading multiple images."""
        uploaded_ids = []

        for image_path in sample_images:
            with open(image_path, "rb") as f:
                response = client.post(
                    "/entities/",
                    files={"image": (image_path.name, f, "image/jpeg")},
                    data={
                        "is_collection": "false",
                        "label": f"Test: {image_path.name}"
                    }
                )

            assert response.status_code == 201
            data = response.json()
            assert "md5" in data
            assert "file_path" in data
            uploaded_ids.append(data["id"])

        # Verify all entities were created
        unique_ids = set(uploaded_ids)
        assert len(unique_ids) > 0

        # Verify we can retrieve all entities
        response = client.get("/entities/?page_size=100")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == len(unique_ids)

        # Verify each entity can be retrieved individually
        for entity_id in unique_ids:
            get_response = client.get(f"/entities/{entity_id}")
            assert get_response.status_code == 200
            assert "md5" in get_response.json()
    
    def test_upload_without_file(self, client):
        """Test creating a collection without a file."""
        response = client.post(
            "/entities/",
            data={
                "is_collection": "true",
                "label": "Test Collection",
                "description": "A collection without files"
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["is_collection"] is True
        assert data["md5"] is None
        assert data["file_size"] is None
    
    def test_metadata_accuracy(self, client, sample_image, clean_media_dir):
        """Test that extracted metadata matches file properties."""
        actual_size = sample_image.stat().st_size
        
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Metadata test"}
            )
        
        assert response.status_code == 201
        data = response.json()
        
        # File size should match
        assert data["file_size"] == actual_size
        
        # Should have dimensions
        assert data["width"] > 0
        assert data["height"] > 0
        
        # Should have MIME type
        assert "image" in data["mime_type"].lower()
        
        # Should have Create Date (if available in sample image)
        # Note: Most test images have EXIF data
        if data["create_date"]:
            assert isinstance(data["create_date"], int)
            assert data["create_date"] > 0
