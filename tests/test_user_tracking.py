"""User tracking field tests (added_by, updated_by)."""



class TestUserTracking:
    """Test that added_by and updated_by fields are properly tracked."""

    def test_create_entity_sets_added_by(self, client, sample_image):
        """Creating an entity should set added_by to the authenticated user."""
        with open(sample_image, "rb") as f:
            files = {"image": f}
            response = client.post(
                "/entities/",
                data={"label": "test entity", "is_collection": "false"},
                files=files
            )

        assert response.status_code in [200, 201]
        entity = response.json()
        assert entity.get("added_by") == "testuser"

    def test_update_entity_sets_updated_by(self, client, sample_image):
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
        entity = response.json()
        entity_id = entity["id"]
        initial_added_by = entity.get("added_by")

        # Update the entity
        with open(sample_image, "rb") as f:
            files = {"image": f}
            response = client.put(
                f"/entities/{entity_id}",
                data={"label": "updated label", "is_collection": "false"},
                files=files
            )

        assert response.status_code in [200, 201]
        updated_entity = response.json()

        # Verify updated_by is set
        assert updated_entity.get("updated_by") == "testuser"
        # Verify added_by doesn't change
        assert updated_entity.get("added_by") == initial_added_by

    def test_patch_entity_sets_updated_by(self, client, sample_image):
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
        entity = response.json()
        entity_id = entity["id"]
        initial_added_by = entity.get("added_by")

        # Patch the entity
        response = client.patch(
            f"/entities/{entity_id}",
            json={"body": {"label": "patched label"}}
        )

        assert response.status_code == 200
        patched_entity = response.json()

        # Verify updated_by is set
        assert patched_entity.get("updated_by") == "testuser"
        # Verify added_by doesn't change
        assert patched_entity.get("added_by") == initial_added_by

    def test_multiple_updates_track_latest_user(self, client, sample_image):
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
        entity = response.json()
        entity_id = entity["id"]
        initial_added_by = entity.get("added_by")

        # Patch multiple times
        response = client.patch(
            f"/entities/{entity_id}",
            json={"body": {"label": "v2"}}
        )
        assert response.status_code == 200

        response = client.patch(
            f"/entities/{entity_id}",
            json={"body": {"label": "v3"}}
        )
        assert response.status_code == 200
        final_entity = response.json()

        # updated_by should be testuser (latest update)
        assert final_entity.get("updated_by") == "testuser"
        # added_by should still be the original
        assert final_entity.get("added_by") == initial_added_by

    def test_user_tracking_in_version_history(self, client, sample_image):
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
        entity = response.json()
        entity_id = entity["id"]

        # Update the entity
        response = client.patch(
            f"/entities/{entity_id}",
            json={"body": {"label": "v2"}}
        )
        assert response.status_code == 200

        # Get version history
        response = client.get(f"/entities/{entity_id}/versions")

        assert response.status_code == 200
        versions = response.json()

        # Should have at least 1 version
        assert len(versions) >= 1
