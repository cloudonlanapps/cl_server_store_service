"""User tracking field tests (added_by, updated_by)."""

from pathlib import Path

from fastapi.testclient import TestClient

from store.db_service.schemas import EntitySchema as Item


class TestUserTracking:
    """Test that added_by and updated_by fields are properly tracked."""

    def test_create_entity_sets_added_by(
        self, client: TestClient, sample_image: Path
    ) -> None:
        """Creating an entity should set added_by to the authenticated user."""
        with open(sample_image, "rb") as f:
            files = {"image": f}
            response = client.post(
                "/entities/",
                data={"label": "test entity", "is_collection": "false"},
                files=files
            )

        assert response.status_code in [200, 201]
        entity = Item.model_validate(response.json())
        assert entity.added_by == "testuser"

    def test_update_entity_sets_updated_by(
        self, client: TestClient, sample_image: Path
    ) -> None:
        """Updating an entity should set updated_by to the current user."""
        # Create entity
        with open(sample_image, "rb") as f:
            files = {"image": f}
            response = client.post(
                "/entities/",
                data={"label": "initial label", "is_collection": "false"},
                files=files
            )

        assert response.status_code in [200, 201]
        entity = Item.model_validate(response.json())
        assert entity.id is not None
        entity_id = entity.id
        initial_added_by = entity.added_by

        # Update the entity
        with open(sample_image, "rb") as f:
            files = {"image": f}
            response = client.put(
                f"/entities/{entity_id}",
                data={"label": "updated label", "is_collection": "false"},
                files=files
            )

        assert response.status_code in [200, 201]
        updated_entity = Item.model_validate(response.json())

        # Verify updated_by is set
        assert updated_entity.updated_by == "testuser"
        # Verify added_by doesn't change
        assert updated_entity.added_by == initial_added_by

    def test_patch_entity_sets_updated_by(
        self, client: TestClient, sample_image: Path
    ) -> None:
        """Patching an entity should set updated_by to the current user."""
        # Create entity
        with open(sample_image, "rb") as f:
            files = {"image": f}
            response = client.post(
                "/entities/",
                data={"label": "initial label", "is_collection": "false"},
                files=files
            )

        assert response.status_code in [200, 201]
        entity = Item.model_validate(response.json())
        assert entity.id is not None
        entity_id = entity.id
        initial_added_by = entity.added_by

        # Patch the entity
        response = client.patch(
            f"/entities/{entity_id}",
            data={"label": "patched label"}
        )

        assert response.status_code == 200
        patched_entity = Item.model_validate(response.json())

        # Verify updated_by is set
        assert patched_entity.updated_by == "testuser"
        # Verify added_by doesn't change
        assert patched_entity.added_by == initial_added_by

    def test_multiple_updates_track_latest_user(
        self, client: TestClient, sample_image: Path
    ) -> None:
        """Multiple updates should track the most recent update time."""
        # Create entity
        with open(sample_image, "rb") as f:
            files = {"image": f}
            response = client.post(
                "/entities/",
                data={"label": "v1", "is_collection": "false"},
                files=files
            )

        assert response.status_code in [200, 201]
        entity = Item.model_validate(response.json())
        assert entity.id is not None
        entity_id = entity.id
        initial_added_by = entity.added_by

        # Patch multiple times
        response = client.patch(
            f"/entities/{entity_id}",
            data={"label": "v2"}
        )
        assert response.status_code == 200

        response = client.patch(
            f"/entities/{entity_id}",
            data={"label": "v3"}
        )
        assert response.status_code == 200
        final_entity = Item.model_validate(response.json())

        # updated_by should be testuser (latest update)
        assert final_entity.updated_by == "testuser"
        # added_by should still be the original
        assert final_entity.added_by == initial_added_by

    def test_user_tracking_in_version_history(
        self, client: TestClient, sample_image: Path
    ) -> None:
        """Version history should track user changes across versions."""
        # Create entity
        with open(sample_image, "rb") as f:
            files = {"image": f}
            response = client.post(
                "/entities/",
                data={"label": "v1", "is_collection": "false"},
                files=files
            )

        assert response.status_code in [200, 201]
        entity = Item.model_validate(response.json())
        assert entity.id is not None
        entity_id = entity.id

        # Update the entity
        response = client.patch(
            f"/entities/{entity_id}",
            data={"label": "v2"}
        )
        assert response.status_code == 200

        # Get version history
        response = client.get(f"/entities/{entity_id}/versions")

        assert response.status_code == 200
        versions: list[dict[str, int | None]] = response.json()

        # Should have at least 1 version
        assert len(versions) >= 1
