"""
Tests for file storage organization and management.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
from store.store.entity_storage import EntityStorageService


class TestFileStorage:
    """Test file storage organization."""

    def test_save_file_organized_directory_structure(self, client, sample_image):
        """Test that files are stored in YYYY/MM/DD structure."""
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
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

    def test_md5_prefix_in_filename(self, client, sample_image):
        """Test that file metadata includes MD5 hash and file can be retrieved."""
        with open(sample_image, "rb") as f:
            response = client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "MD5 Name Test"}
            )

        assert response.status_code == 201
        data = response.json()

        # Verify MD5 is present and file_path is set
        assert "md5" in data
        assert "file_path" in data
        md5 = data["md5"]
        file_path = data["file_path"]

        # Filename should contain MD5
        assert md5 in file_path
        assert file_path.endswith(sample_image.suffix)

        # Verify entity can be retrieved
        entity_id = data["id"]
        get_response = client.get(f"/entities/{entity_id}")
        assert get_response.status_code == 200

    def test_multiple_files_organization(self, client, sample_images):
        """Test that multiple files can be uploaded and retrieved."""
        entity_ids = []

        for image_path in sample_images:
            with open(image_path, "rb") as f:
                response = client.post(
                    "/entities/",
                    files={"image": (image_path.name, f, "image/jpeg")},
                    data={"is_collection": "false", "label": f"Test {image_path.name}"}
                )
            assert response.status_code == 201
            entity_ids.append(response.json()["id"])

        # Verify all entities were created
        assert len(entity_ids) == len(sample_images)

        # Verify all can be retrieved
        for entity_id in entity_ids:
            get_response = client.get(f"/entities/{entity_id}")
            assert get_response.status_code == 200
            assert "md5" in get_response.json()
            assert "file_path" in get_response.json()

    def test_file_deletion_on_entity_update(self, client, sample_images):
        """Test that entity can be updated with a new file."""
        if len(sample_images) < 2:
            return  # Skip if not enough images

        image1, image2 = sample_images[0], sample_images[1]

        # Upload first image
        with open(image1, "rb") as f:
            response1 = client.post(
                "/entities/",
                files={"image": (image1.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Original"}
            )

        assert response1.status_code == 201
        entity_id = response1.json()["id"]
        md5_1 = response1.json()["md5"]

        # Update with second image
        with open(image2, "rb") as f:
            response2 = client.put(
                f"/entities/{entity_id}",
                files={"image": (image2.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "Updated"}
            )

        assert response2.status_code == 200
        updated_data = response2.json()
        md5_2 = updated_data["md5"]

        # Verify MD5 changed (different file)
        assert md5_2 != md5_1
        assert updated_data["label"] == "Updated"

        # Verify entity still exists and has new data
        get_response = client.get(f"/entities/{entity_id}")
        assert get_response.status_code == 200
        assert get_response.json()["md5"] == md5_2

    def test_delete_file_nonexistent(self, file_storage_service):
        """Test deleting a file that doesn't exist."""
        assert file_storage_service.delete_file("nonexistent.jpg") is False

    def test_delete_file_exception(self, file_storage_service):
        """Test exception handling in delete_file."""
        with patch("pathlib.Path.unlink", side_effect=Exception("Unlink failed")):
            # Create a real file first so it gets past the exists() check
            p = file_storage_service.base_dir / "error.jpg"
            p.write_bytes(b"test")
            assert file_storage_service.delete_file("error.jpg") is False

    def test_cleanup_empty_dirs(self, file_storage_service):
        """Test recursive cleanup of empty directories."""
        # Create nested structure: base/a/b/c/file.txt
        rel_path = Path("a/b/c/file.txt")
        abs_path = file_storage_service.base_dir / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text("content")
        
        # Delete file and trigger cleanup
        assert file_storage_service.delete_file(str(rel_path)) is True
        
        # Verify directories a/b/c are gone
        assert not (file_storage_service.base_dir / "a").exists()
        # Verify base dir still exists
        assert file_storage_service.base_dir.exists()

    def test_get_storage_path_no_extension(self, file_storage_service):
        """Test suffix extraction from original filename when metadata lacks extension."""
        metadata = {"md5": "noext"}
        path = file_storage_service.get_storage_path(metadata, "image.png")
        assert path.suffix == ".png"
        assert path.name == "noext.png"

    def test_get_storage_path_with_extension_prefix(self, file_storage_service):
        """Test extension handling when it already starts with dot."""
        metadata = {"md5": "withdot", "extension": ".jpg"}
        path = file_storage_service.get_storage_path(metadata, "ignored.png")
        assert path.name == "withdot.jpg"
