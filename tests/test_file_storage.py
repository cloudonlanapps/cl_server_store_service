"""
Tests for file storage organization and management.
"""

from pathlib import Path


class TestFileStorage:
    """Test file storage organization."""
    
    def test_file_storage_structure(self, client, sample_image, clean_media_dir):
        """Test that files are stored in YYYY/MM/DD structure."""
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entity/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Storage Test"}
            )
        
        assert response.status_code == 201
        data = response.json()
        
        # Check file path in response (should be relative)
        file_path = Path(data["file_path"])
        
        # Check structure: YYYY/MM/DD/{md5}.{ext}
        # Parts: [YYYY, MM, DD, filename]
        assert len(file_path.parts) >= 4
        
        # Verify filename format (MD5 + extension)
        filename = file_path.name
        md5 = data["md5"]
        assert filename.startswith(md5)
        assert filename.endswith(Path(sample_image.name).suffix)
        # Should NOT contain original filename stem (unless it was part of extension which is unlikely)
        assert sample_image.stem not in filename

    def test_md5_naming_convention(self, file_storage_service):
        """Test that files are named with {md5}.{ext} convention."""
        file_bytes = b"test content"
        metadata = {"md5": "abc1234567890def", "extension": "jpg"}
        original_filename = "test_image.jpg"
        
        relative_path = file_storage_service.save_file(file_bytes, metadata, original_filename)
        
        # Should contain MD5
        assert "abc1234567890def" in relative_path
        # Should NOT contain original filename
        assert "test_image" not in relative_path
        # Should end with extension
        assert relative_path.endswith(".jpg")
        # Should be in YYYY/MM/DD structure
        assert len(Path(relative_path).parts) >= 4
    
    def test_md5_prefix_in_filename(self, client, sample_image, clean_media_dir):
        """Test that filenames use MD5 as name."""
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entity/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "MD5 Name Test"}
            )
        
        data = response.json()
        file_path = data["file_path"]
        md5 = data["md5"]
        
        # Filename should be {md5}.{ext}
        assert md5 in file_path
        assert sample_image.name not in file_path  # Original name should NOT be present
        assert file_path.endswith(sample_image.suffix)
        
        # Also verify on disk
        stored_files = list(clean_media_dir.rglob("*.jpg"))
        assert len(stored_files) == 1
        
        filename = stored_files[0].name
        assert filename.startswith(md5)
        assert not (sample_image.stem in filename and sample_image.stem != md5) # Ensure original stem is not part of filename unless it's the MD5 itself
    
    def test_multiple_files_organization(self, client, sample_images, clean_media_dir):
        """Test that multiple files are organized correctly."""
        for image_path in sample_images:
            with open(image_path, "rb") as f:
                response = client.post(
                    "/entity/",
                    files={"image": (image_path.name, f, "image/jpeg")},
                    data={"is_collection": "false", "label": f"Test {image_path.name}"}
                )
            assert response.status_code == 201
        
        # All files should be stored
        stored_files = list(clean_media_dir.rglob("*.jpg"))
        assert len(stored_files) == len(sample_images)
        
        # All should follow YYYY/MM/DD structure
        for stored_file in stored_files:
            rel_path = stored_file.relative_to(clean_media_dir)
            assert len(rel_path.parts) == 4
    
    def test_file_deletion_on_entity_update(self, client, sample_images, clean_media_dir):
        """Test that old file is deleted when entity is updated with new file."""
        if len(sample_images) < 2:
            return  # Skip if not enough images
        
        image1, image2 = sample_images[0], sample_images[1]
        
        # Upload first image
        with open(image1, "rb") as f:
            response1 = client.post(
                "/entity/",
                files={"image": (image1.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Original"}
            )
        
        assert response1.status_code == 201
        entity_id = response1.json()["id"]
        md5_1 = response1.json()["md5"]
        
        # Verify first file exists
        files_before = list(clean_media_dir.rglob("*.jpg"))
        assert len(files_before) == 1
        assert md5_1 in str(files_before[0])
        
        # Update with second image
        with open(image2, "rb") as f:
            response2 = client.put(
                f"/entity/{entity_id}",
                files={"image": (image2.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Updated"}
            )
        
        assert response2.status_code == 200
        md5_2 = response2.json()["md5"]
        
        # Verify only second file exists
        files_after = list(clean_media_dir.rglob("*.jpg"))
        assert len(files_after) == 1
        assert md5_2 in str(files_after[0])
        assert md5_1 not in str(files_after[0])
