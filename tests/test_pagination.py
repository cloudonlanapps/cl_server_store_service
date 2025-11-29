"""
Tests for pagination functionality with versioning support.
"""

import pytest


class TestPagination:
    """Test pagination for GET /entity/ endpoint."""
    
    def test_pagination_first_page(self, client, sample_images):
        """Test that first page returns correct items with versioning enabled."""
        # Create 15 entities to test pagination
        created_ids = []
        for i, image in enumerate(sample_images[:15]):
            with open(image, "rb") as f:
                response = client.post(
                    "/entity/",
                    files={"image": (image.name, f, "image/jpeg")},
                    data={
                        "is_collection": "false",
                        "label": f"Entity {i+1}"
                    }
                )
            assert response.status_code == 201
            created_ids.append(response.json()["id"])
        
        # Get first page with page_size=10
        response = client.get("/entity/?page=1&page_size=10")
        assert response.status_code == 200
        
        data = response.json()
        assert "items" in data
        assert "pagination" in data
        
        # Should have 10 items on first page
        assert len(data["items"]) == 10
        
        # Check pagination metadata
        pagination = data["pagination"]
        assert pagination["page"] == 1
        assert pagination["page_size"] == 10
        assert pagination["total_items"] == 15
        assert pagination["total_pages"] == 2
        assert pagination["has_next"] is True
        assert pagination["has_prev"] is False
    
    def test_pagination_second_page(self, client, sample_images):
        """Test that second page returns different items."""
        # Create 15 entities
        for i, image in enumerate(sample_images[:15]):
            with open(image, "rb") as f:
                client.post(
                    "/entity/",
                    files={"image": (image.name, f, "image/jpeg")},
                    data={"is_collection": "false", "label": f"Entity {i+1}"}
                )
        
        # Get first page
        page1_response = client.get("/entity/?page=1&page_size=10")
        page1_ids = {item["id"] for item in page1_response.json()["items"]}
        
        # Get second page
        page2_response = client.get("/entity/?page=2&page_size=10")
        assert page2_response.status_code == 200
        
        data = page2_response.json()
        assert len(data["items"]) == 5  # Only 5 items on second page
        
        # Items should be different from first page
        page2_ids = {item["id"] for item in data["items"]}
        assert len(page1_ids & page2_ids) == 0  # No overlap
        
        # Check pagination metadata
        pagination = data["pagination"]
        assert pagination["page"] == 2
        assert pagination["has_next"] is False
        assert pagination["has_prev"] is True
    
    def test_pagination_custom_page_size(self, client, sample_images):
        """Test with different page sizes."""
        # Create 20 entities
        for i, image in enumerate(sample_images[:20]):
            with open(image, "rb") as f:
                client.post(
                    "/entity/",
                    files={"image": (image.name, f, "image/jpeg")},
                    data={"is_collection": "false", "label": f"Entity {i+1}"}
                )
        
        # Test page_size=5
        response = client.get("/entity/?page=1&page_size=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5
        assert data["pagination"]["total_pages"] == 4
        
        # Test page_size=25 (should return all 20)
        response = client.get("/entity/?page=1&page_size=25")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 20
        assert data["pagination"]["total_pages"] == 1
    
    def test_pagination_metadata(self, client, sample_images):
        """Test that pagination metadata is accurate."""
        # Create 23 entities
        for i, image in enumerate(sample_images[:23]):
            with open(image, "rb") as f:
                client.post(
                    "/entity/",
                    files={"image": (image.name, f, "image/jpeg")},
                    data={"is_collection": "false", "label": f"Entity {i+1}"}
                )
        
        response = client.get("/entity/?page=2&page_size=10")
        assert response.status_code == 200
        
        pagination = response.json()["pagination"]
        assert pagination["page"] == 2
        assert pagination["page_size"] == 10
        assert pagination["total_items"] == 23
        assert pagination["total_pages"] == 3
        assert pagination["has_next"] is True
        assert pagination["has_prev"] is True
    
    def test_pagination_last_page(self, client, sample_images):
        """Test last page with partial results."""
        # Create 23 entities
        for i, image in enumerate(sample_images[:23]):
            with open(image, "rb") as f:
                client.post(
                    "/entity/",
                    files={"image": (image.name, f, "image/jpeg")},
                    data={"is_collection": "false", "label": f"Entity {i+1}"}
                )
        
        # Get last page (page 3)
        response = client.get("/entity/?page=3&page_size=10")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["items"]) == 3  # Only 3 items on last page
        
        pagination = data["pagination"]
        assert pagination["has_next"] is False
        assert pagination["has_prev"] is True
    
    def test_pagination_beyond_total(self, client, sample_images):
        """Test page number beyond total pages."""
        # Create 10 entities
        for i, image in enumerate(sample_images[:10]):
            with open(image, "rb") as f:
                client.post(
                    "/entity/",
                    files={"image": (image.name, f, "image/jpeg")},
                    data={"is_collection": "false", "label": f"Entity {i+1}"}
                )
        
        # Request page 10 (beyond total)
        response = client.get("/entity/?page=10&page_size=10")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["items"]) == 0  # No items
        assert data["pagination"]["total_items"] == 10
        assert data["pagination"]["total_pages"] == 1


class TestPaginationWithVersioning:
    """Test pagination with versioning support."""
    
    def test_pagination_with_version_parameter(self, client, sample_images):
        """Test querying all entities at version 1."""
        # Create 10 entities
        entity_ids = []
        for i, image in enumerate(sample_images[:10]):
            with open(image, "rb") as f:
                response = client.post(
                    "/entity/",
                    files={"image": (image.name, f, "image/jpeg")},
                    data={"is_collection": "false", "label": f"Original {i+1}"}
                )
            entity_ids.append(response.json()["id"])
        
        # Update first 5 entities to create version 2
        for entity_id in entity_ids[:5]:
            client.put(
                f"/entity/{entity_id}",
                data={"is_collection": "false", "label": f"Updated {entity_id}"}
            )
        
        # Query all entities at version 1 (original state)
        response = client.get("/entity/?page=1&page_size=10&version=1")
        assert response.status_code == 200
        
        data = response.json()
        items = data["items"]
        
        # All items should have "Original" in label (version 1)
        for item in items:
            assert "Original" in item["label"]
            assert "Updated" not in item["label"]
    
    def test_pagination_version_across_pages(self, client, sample_images):
        """Test that version parameter works across multiple pages."""
        # Create 15 entities
        for i, image in enumerate(sample_images[:15]):
            with open(image, "rb") as f:
                client.post(
                    "/entity/",
                    files={"image": (image.name, f, "image/jpeg")},
                    data={"is_collection": "false", "label": f"V1 Entity {i+1}"}
                )
        
        # Update all entities
        for i in range(1, 16):
            client.put(
                f"/entity/{i}",
                data={"is_collection": "false", "label": f"V2 Entity {i}"}
            )
        
        # Get page 1 at version 1
        page1 = client.get("/entity/?page=1&page_size=10&version=1")
        assert all("V1" in item["label"] for item in page1.json()["items"])
        
        # Get page 2 at version 1
        page2 = client.get("/entity/?page=2&page_size=10&version=1")
        assert all("V1" in item["label"] for item in page2.json()["items"])
        
        # Get page 1 at version 2 (latest)
        page1_v2 = client.get("/entity/?page=1&page_size=10&version=2")
        assert all("V2" in item["label"] for item in page1_v2.json()["items"])
    
    def test_pagination_version_nonexistent(self, client, sample_images):
        """Test with version that doesn't exist for some entities."""
        # Create 10 entities
        for i, image in enumerate(sample_images[:10]):
            with open(image, "rb") as f:
                client.post(
                    "/entity/",
                    files={"image": (image.name, f, "image/jpeg")},
                    data={"is_collection": "false", "label": f"Entity {i+1}"}
                )
        
        # Update only first 5 entities (they have version 2)
        for i in range(1, 6):
            client.put(
                f"/entity/{i}",
                data={"is_collection": "false", "label": f"Updated {i}"}
            )
        
        # Query version 2 - should only return 5 items (entities 1-5)
        response = client.get("/entity/?page=1&page_size=10&version=2")
        assert response.status_code == 200
        
        data = response.json()
        # Only entities with version 2 should be returned
        assert len(data["items"]) == 5
    
    def test_pagination_version_metadata_accuracy(self, client, sample_images):
        """Test that versioned entities have correct historical data."""
        # Create entities with specific labels
        original_labels = []
        for i, image in enumerate(sample_images[:10]):
            label = f"Original Label {i+1}"
            original_labels.append(label)
            with open(image, "rb") as f:
                client.post(
                    "/entity/",
                    files={"image": (image.name, f, "image/jpeg")},
                    data={"is_collection": "false", "label": label}
                )
        
        # Update all entities with new labels
        for i in range(1, 11):
            client.put(
                f"/entity/{i}",
                data={"is_collection": "false", "label": f"Updated Label {i}"}
            )
        
        # Query version 1 - should have original labels
        response = client.get("/entity/?page=1&page_size=10&version=1")
        items = response.json()["items"]
        
        for i, item in enumerate(items):
            # Labels should match original labels
            assert item["label"] in original_labels


class TestPaginationEdgeCases:
    """Test edge cases for pagination."""
    
    def test_pagination_empty_database(self, client):
        """Test pagination with no entities."""
        response = client.get("/entity/?page=1&page_size=10")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["items"]) == 0
        assert data["pagination"]["total_items"] == 0
        assert data["pagination"]["total_pages"] == 0
        assert data["pagination"]["has_next"] is False
        assert data["pagination"]["has_prev"] is False
    
    def test_pagination_invalid_page_zero(self, client):
        """Test that page=0 is rejected."""
        response = client.get("/entity/?page=0&page_size=10")
        # Should return validation error (422)
        assert response.status_code == 422
    
    def test_pagination_invalid_page_negative(self, client):
        """Test that negative page is rejected."""
        response = client.get("/entity/?page=-1&page_size=10")
        assert response.status_code == 422
    
    def test_pagination_invalid_page_size_zero(self, client):
        """Test that page_size=0 is rejected."""
        response = client.get("/entity/?page=1&page_size=0")
        assert response.status_code == 422
    
    def test_pagination_max_page_size(self, client):
        """Test that page_size > 100 is rejected."""
        response = client.get("/entity/?page=1&page_size=101")
        # Should return validation error
        assert response.status_code == 422
    
    def test_pagination_total_count_accuracy(self, client, sample_images):
        """Test that total count matches actual entities."""
        # Create exactly 17 entities
        for i, image in enumerate(sample_images[:17]):
            with open(image, "rb") as f:
                client.post(
                    "/entity/",
                    files={"image": (image.name, f, "image/jpeg")},
                    data={"is_collection": "false", "label": f"Entity {i+1}"}
                )
        
        # Query with different page sizes
        for page_size in [5, 10, 20]:
            response = client.get(f"/entity/?page=1&page_size={page_size}")
            assert response.json()["pagination"]["total_items"] == 17
