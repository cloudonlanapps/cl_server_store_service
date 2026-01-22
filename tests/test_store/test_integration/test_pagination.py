"""
Tests for pagination functionality with versioning support.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from store.common.schemas import Item, PaginatedResponse


class TestPagination:
    """Test pagination for GET /entities/ endpoint."""

    def test_pagination_first_page(
        self, client: TestClient, sample_images: list[Path]
    ) -> None:
        """Test that first page returns correct items with versioning enabled."""
        # Create 15 entities to test pagination
        created_ids: list[int] = []
        for i, image in enumerate(sample_images[:15]):
            with open(image, "rb") as f:
                response = client.post(
                    "/entities/",
                    files={"image": (f"image_{i}.jpg", f, "image/jpeg")},
                    data={
                        "is_collection": "false",
                        "label": f"Entity {i+1}"
                    }
                )
            assert response.status_code == 201
            item = Item.model_validate(response.json())
            assert item.id is not None
            created_ids.append(item.id)

        # Get first page with page_size=10
        response = client.get("/entities/?page=1&page_size=10")
        assert response.status_code == 200

        paginated = PaginatedResponse.model_validate(response.json())

        # Should have 10 items on first page
        assert len(paginated.items) == 10

        # Check pagination metadata
        assert paginated.pagination.page == 1
        assert paginated.pagination.page_size == 10
        assert paginated.pagination.total_items == 15
        assert paginated.pagination.total_pages == 2
        assert paginated.pagination.has_next is True
        assert paginated.pagination.has_prev is False

    def test_pagination_second_page(
        self, client: TestClient, sample_images: list[Path]
    ) -> None:
        """Test that second page returns different items."""
        # Create 15 entities
        for i, image in enumerate(sample_images[:15]):
            with open(image, "rb") as f:
                _ = client.post(
                    "/entities/",
                    files={"image": (f"image_page2_{i}.jpg", f, "image/jpeg")},
                    data={"is_collection": "false", "label": f"Entity {i+1}"}
                )

        # Get first page
        page1_response = client.get("/entities/?page=1&page_size=10")
        page1 = PaginatedResponse.model_validate(page1_response.json())
        page1_ids = {item.id for item in page1.items if item.id is not None}

        # Get second page
        page2_response = client.get("/entities/?page=2&page_size=10")
        assert page2_response.status_code == 200

        page2 = PaginatedResponse.model_validate(page2_response.json())
        assert len(page2.items) == 5  # Only 5 items on second page

        # Items should be different from first page
        page2_ids = {item.id for item in page2.items if item.id is not None}
        assert len(page1_ids & page2_ids) == 0  # No overlap

        # Check pagination metadata
        assert page2.pagination.page == 2
        assert page2.pagination.has_next is False
        assert page2.pagination.has_prev is True

    def test_pagination_custom_page_size(
        self, client: TestClient, sample_images: list[Path]
    ) -> None:
        """Test with different page sizes."""
        # Create 20 entities
        for i, image in enumerate(sample_images[:20]):
            with open(image, "rb") as f:
                _ = client.post(
                    "/entities/",
                    files={"image": (f"image_custom_{i}.jpg", f, "image/jpeg")},
                    data={"is_collection": "false", "label": f"Entity {i+1}"}
                )

        # Test page_size=5
        response = client.get("/entities/?page=1&page_size=5")
        assert response.status_code == 200
        paginated = PaginatedResponse.model_validate(response.json())
        assert len(paginated.items) == 5
        assert paginated.pagination.total_pages == 4

        # Test page_size=25 (should return all 20)
        response = client.get("/entities/?page=1&page_size=25")
        assert response.status_code == 200
        paginated = PaginatedResponse.model_validate(response.json())
        assert len(paginated.items) == 20
        assert paginated.pagination.total_pages == 1

    def test_pagination_metadata(
        self, client: TestClient, sample_images: list[Path]
    ) -> None:
        """Test that pagination metadata is accurate."""
        # Create 23 entities
        for i, image in enumerate(sample_images[:23]):
            with open(image, "rb") as f:
                _ = client.post(
                    "/entities/",
                    files={"image": (image.name, f, "image/jpeg")},
                    data={"is_collection": "false", "label": f"Entity {i+1}"}
                )

        response = client.get("/entities/?page=2&page_size=10")
        assert response.status_code == 200

        paginated = PaginatedResponse.model_validate(response.json())
        assert paginated.pagination.page == 2
        assert paginated.pagination.page_size == 10
        assert paginated.pagination.total_items == 23
        assert paginated.pagination.total_pages == 3
        assert paginated.pagination.has_next is True
        assert paginated.pagination.has_prev is True

    def test_pagination_last_page(
        self, client: TestClient, sample_images: list[Path]
    ) -> None:
        """Test last page with partial results."""
        # Create 23 entities
        for i, image in enumerate(sample_images[:23]):
            with open(image, "rb") as f:
                _ = client.post(
                    "/entities/",
                    files={"image": (image.name, f, "image/jpeg")},
                    data={"is_collection": "false", "label": f"Entity {i+1}"}
                )

        # Get last page (page 3)
        response = client.get("/entities/?page=3&page_size=10")
        assert response.status_code == 200

        paginated = PaginatedResponse.model_validate(response.json())
        assert len(paginated.items) == 3  # Only 3 items on last page

        assert paginated.pagination.has_next is False
        assert paginated.pagination.has_prev is True

    def test_pagination_beyond_total(
        self, client: TestClient, sample_images: list[Path]
    ) -> None:
        """Test page number beyond total pages."""
        # Create 10 entities
        for i, image in enumerate(sample_images[:10]):
            with open(image, "rb") as f:
                _ = client.post(
                    "/entities/",
                    files={"image": (image.name, f, "image/jpeg")},
                    data={"is_collection": "false", "label": f"Entity {i+1}"}
                )

        # Request page 10 (beyond total)
        response = client.get("/entities/?page=10&page_size=10")
        assert response.status_code == 200

        paginated = PaginatedResponse.model_validate(response.json())
        assert len(paginated.items) == 0  # No items
        assert paginated.pagination.total_items == 10
        assert paginated.pagination.total_pages == 1


class TestPaginationWithVersioning:
    """Test pagination with versioning support."""

    def test_pagination_with_version_parameter(
        self, client: TestClient, sample_images: list[Path]
    ) -> None:
        """Test querying all entities at version 1."""
        # Create 10 entities
        entity_ids: list[int] = []
        for i, image in enumerate(sample_images[:10]):
            with open(image, "rb") as f:
                response = client.post(
                    "/entities/",
                    files={"image": (image.name, f, "image/jpeg")},
                    data={"is_collection": "false", "label": f"Original {i+1}"}
                )
            item = Item.model_validate(response.json())
            assert item.id is not None
            entity_ids.append(item.id)

        # Update first 5 entities to create version 2
        for entity_id in entity_ids[:5]:
            _ = client.put(
                f"/entities/{entity_id}",
                data={"is_collection": "false", "label": f"Updated {entity_id}"}
            )

        # Query all entities at version 1 (original state)
        response = client.get("/entities/?page=1&page_size=10&version=1")
        assert response.status_code == 200

        paginated = PaginatedResponse.model_validate(response.json())

        # All items should have "Original" in label (version 1)
        for item in paginated.items:
            assert item.label is not None
            assert "Original" in item.label
            assert "Updated" not in item.label

    def test_pagination_version_across_pages(
        self, client: TestClient, sample_images: list[Path]
    ) -> None:
        """Test that version parameter works across multiple pages."""
        # Create 15 entities
        for i, image in enumerate(sample_images[:15]):
            with open(image, "rb") as f:
                _ = client.post(
                    "/entities/",
                    files={"image": (image.name, f, "image/jpeg")},
                    data={"is_collection": "false", "label": f"V1 Entity {i+1}"}
                )

        # Update all entities
        for i in range(1, 16):
            _ = client.put(
                f"/entities/{i}",
                data={"is_collection": "false", "label": f"V2 Entity {i}"}
            )

        # Get page 1 at version 1
        page1_response = client.get("/entities/?page=1&page_size=10&version=1")
        page1 = PaginatedResponse.model_validate(page1_response.json())
        assert all(
            item.label is not None and "V1" in item.label for item in page1.items
        )

        # Get page 2 at version 1
        page2_response = client.get("/entities/?page=2&page_size=10&version=1")
        page2 = PaginatedResponse.model_validate(page2_response.json())
        assert all(
            item.label is not None and "V1" in item.label for item in page2.items
        )

        # Get page 1 at version 2 (latest)
        page1_v2_response = client.get("/entities/?page=1&page_size=10&version=2")
        page1_v2 = PaginatedResponse.model_validate(page1_v2_response.json())
        assert all(
            item.label is not None and "V2" in item.label for item in page1_v2.items
        )

    def test_pagination_version_nonexistent(
        self, client: TestClient, sample_images: list[Path]
    ) -> None:
        """Test with version that doesn't exist for some entities."""
        # Create 10 entities
        for i, image in enumerate(sample_images[:10]):
            with open(image, "rb") as f:
                _ = client.post(
                    "/entities/",
                    files={"image": (image.name, f, "image/jpeg")},
                    data={"is_collection": "false", "label": f"Entity {i+1}"}
                )

        # Update only first 5 entities (they have version 2)
        for i in range(1, 6):
            _ = client.put(
                f"/entities/{i}",
                data={"is_collection": "false", "label": f"Updated {i}"}
            )

        # Query version 2 - should only return 5 items (entities 1-5)
        response = client.get("/entities/?page=1&page_size=10&version=2")
        assert response.status_code == 200

        paginated = PaginatedResponse.model_validate(response.json())
        # Only entities with version 2 should be returned
        assert len(paginated.items) == 5

    def test_pagination_version_metadata_accuracy(
        self, client: TestClient, sample_images: list[Path]
    ) -> None:
        """Test that versioned entities have correct historical data."""
        # Create entities with specific labels
        original_labels: list[str] = []
        for i, image in enumerate(sample_images[:10]):
            label = f"Original Label {i+1}"
            original_labels.append(label)
            with open(image, "rb") as f:
                _ = client.post(
                    "/entities/",
                    files={"image": (image.name, f, "image/jpeg")},
                    data={"is_collection": "false", "label": label}
                )

        # Update all entities with new labels
        for i in range(1, 11):
            _ = client.put(
                f"/entities/{i}",
                data={"is_collection": "false", "label": f"Updated Label {i}"}
            )

        # Query version 1 - should have original labels
        response = client.get("/entities/?page=1&page_size=10&version=1")
        paginated = PaginatedResponse.model_validate(response.json())

        for item in paginated.items:
            # Labels should match original labels
            assert item.label in original_labels


class TestPaginationEdgeCases:
    """Test edge cases for pagination."""

    def test_pagination_empty_database(self, client: TestClient) -> None:
        """Test pagination with no entities."""
        response = client.get("/entities/?page=1&page_size=10")
        assert response.status_code == 200

        paginated = PaginatedResponse.model_validate(response.json())
        assert len(paginated.items) == 0
        assert paginated.pagination.total_items == 0
        assert paginated.pagination.total_pages == 0
        assert paginated.pagination.has_next is False
        assert paginated.pagination.has_prev is False

    def test_pagination_invalid_page_zero(self, client: TestClient) -> None:
        """Test that page=0 is rejected."""
        response = client.get("/entities/?page=0&page_size=10")
        # Should return validation error (422)
        assert response.status_code == 422

    def test_pagination_invalid_page_negative(self, client: TestClient) -> None:
        """Test that negative page is rejected."""
        response = client.get("/entities/?page=-1&page_size=10")
        assert response.status_code == 422

    def test_pagination_invalid_page_size_zero(self, client: TestClient) -> None:
        """Test that page_size=0 is rejected."""
        response = client.get("/entities/?page=1&page_size=0")
        assert response.status_code == 422

    def test_pagination_max_page_size(self, client: TestClient) -> None:
        """Test that page_size > 100 is rejected."""
        response = client.get("/entities/?page=1&page_size=101")
        # Should return validation error
        assert response.status_code == 422

    def test_pagination_total_count_accuracy(
        self, client: TestClient, sample_images: list[Path]
    ) -> None:
        """Test that total count matches actual entities."""
        # Create exactly 17 entities
        for i, image in enumerate(sample_images[:17]):
            with open(image, "rb") as f:
                _ = client.post(
                    "/entities/",
                    files={"image": (image.name, f, "image/jpeg")},
                    data={"is_collection": "false", "label": f"Entity {i+1}"}
                )

        # Query with different page sizes
        for page_size in [5, 10, 20]:
            response = client.get(f"/entities/?page=1&page_size={page_size}")
            paginated = PaginatedResponse.model_validate(response.json())
            assert paginated.pagination.total_items == 17
