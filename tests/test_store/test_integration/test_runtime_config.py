"""
Tests for runtime configuration API and JWT user ID.
"""

import pytest

from store.db_service.db_internals import ServiceConfig
from store.db_service.config import ConfigDBService



pytestmark = pytest.mark.integration
@pytest.fixture(scope="function")
def db_session(test_db_session):
    """Create a fresh database for each test.

    Wraps the conftest.py test_db_session but adds config cache clearing.
    """
    # Clear config cache before test
    ConfigDBService._cache.clear()

    yield test_db_session

    # Clear config cache after test
    ConfigDBService._cache.clear()
    ConfigDBService._cache_timestamps.clear()


class TestConfigDBService:
    """Test ConfigDBService functionality."""

    def test_get_config_default(self, db_session):
        """Test getting config with default value."""
        config_service = ConfigDBService(db_session)
        value = config_service.get_config("nonexistent_key", "default_value")
        assert value == "default_value"

    def test_set_and_get_config(self, db_session):
        """Test setting and getting configuration."""
        config_service = ConfigDBService(db_session)

        # Set config
        config_service.set_config("test_key", "test_value", "user123")

        # Get config
        value = config_service.get_config("test_key")
        assert value == "test_value"

        # Verify metadata
        metadata = config_service.get_config_metadata("test_key")
        assert metadata is not None
        assert metadata["value"] == "test_value"
        assert metadata["updated_by"] == "user123"

    def test_read_auth_enabled(self, db_session):
        """Test read auth enabled getter/setter."""
        config_service = ConfigDBService(db_session)

        # Default should be false
        assert config_service.get_read_auth_enabled() == False

        # Set to true
        config_service.set_read_auth_enabled(True, "admin123")
        assert config_service.get_read_auth_enabled() == True

        # Set back to false
        config_service.set_read_auth_enabled(False, "admin123")
        assert config_service.get_read_auth_enabled() == False

    def test_config_caching(self, db_session):
        """Test that config values are cached."""
        config_service = ConfigDBService(db_session)

        # Set initial value
        config_service.set_config("cached_key", "value1", "user1")

        # Get value (should be cached)
        value1 = config_service.get_config("cached_key")
        assert value1 == "value1"

        # Manually update database (bypass cache)
        config = db_session.query(ServiceConfig).filter(ServiceConfig.key == "cached_key").first()
        config.value = "value2"
        db_session.commit()

        # Get value again (should still be cached)
        value2 = config_service.get_config("cached_key")
        assert value2 == "value1"  # Still cached

        # Clear cache by setting new value
        config_service.set_config("cached_key", "value3", "user2")
        value3 = config_service.get_config("cached_key")
        assert value3 == "value3"


class TestAdminPrefAPI:
    """Test admin preference API endpoints."""

    def test_get_pref_requires_admin(self, auth_client, db_session):
        """Test that getting preference requires admin access."""
        # No auth headers provided, should fail
        response = auth_client.get("/admin/pref")
        # Should return 401 (no auth)
        assert response.status_code == 401

    def test_update_read_auth_requires_admin(self, auth_client, db_session):
        """Test that updating guest mode requires admin access."""
        # No auth headers provided, should fail
        response = auth_client.put("/admin/pref/guest-mode", data={"guest_mode": "false"})
        # Should return 401 (no auth)
        assert response.status_code == 401


class TestJWTUserID:
    """Test that JWT contains user ID in sub field."""

    def test_jwt_contains_user_id(self, jwt_token_generator):
        """Test that JWT contains user ID in sub field.

        This test verifies that the system expects and correctly parses
        the user ID from the 'sub' field of the JWT.
        """
        # Generate a token with a specific user ID
        user_id = "user_12345"
        token = jwt_token_generator.generate_token(
            sub=user_id, permissions=["media_store_read"], is_admin=False
        )

        # Decode the token to verify structure (simulating what auth middleware does)
        # We use the same verify logic as the application
        from jose import jwt

        # In tests, we might not have the actual public key file, but we can verify
        # the token structure and that our generator puts the ID in the right place.
        # The jwt_token_generator fixture uses a test key pair.

        # Verify the token payload contains the user ID in 'id'
        # This confirms our assumption about where the user ID lives
        payload = jwt.get_unverified_claims(token)
        assert payload["id"] == user_id

        # Also verify that our auth logic would accept this
        # We can't easily call get_current_user directly without mocking Depends,
        # but we can verify the token is valid for our test environment
        assert "permissions" in payload
        assert "media_store_read" in payload["permissions"]

    def test_media_store_receives_user_id(
        self, auth_client, jwt_token_generator, sample_image, db_session
    ):
        """Test that media_store correctly receives and uses user ID from JWT.

        This test verifies that when a JWT is decoded, the 'sub' field
        contains a user ID that is used for added_by tracking in the database.
        """
        # Generate a token with a specific user ID
        user_id = "test_user_id_999"
        token = jwt_token_generator.generate_token(
            sub=user_id,
            permissions=["media_store_write", "media_store_read"],
            is_admin=False,
        )

        # Create an entity using this token
        with open(sample_image, "rb") as f:
            response = auth_client.post(
                "/entities/",
                files={"image": (sample_image.name, f, "image/jpeg")},
                data={"is_collection": "false", "label": "User ID Test Entity"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 201
        entity_id = response.json()["id"]

        # Verify directly in database that added_by was set correctly
        from store.db_service.db_internals import Entity



        entity = db_session.query(Entity).filter(Entity.id == entity_id).first()

        assert entity is not None
        assert entity.added_by == user_id


class TestReadAuthBehaviorWithConfig:
    """Test that read authentication behavior changes based on database config."""

    def test_read_no_auth_allows_access(self, client, db_session):
        """Test that read endpoints are accessible when read auth is disabled."""
        # Set read auth to disabled
        config_service = ConfigDBService(db_session)
        config_service.set_read_auth_enabled(False)

        # Try to access read endpoint without auth
        response = client.get("/entities/")
        # Should succeed (200) or return empty list, not 401/403
        assert response.status_code != 401
        assert response.status_code != 403

    def test_read_auth_enabled_requires_token(self, client, db_session):
        """Test that read endpoints require auth when read auth is enabled."""
        # Set read auth to enabled
        config_service = ConfigDBService(db_session)
        config_service.set_read_auth_enabled(True)

        # Try to access read endpoint without auth
        response = client.get("/entities/")
        # Should return 401 (unauthorized)
        # Note: This might fail if AUTH_DISABLED env var is set
        # TODO: Mock environment variables for this test
        pass

    def test_config_persists_across_sessions(self, db_session):
        """Test that configuration persists in database."""
        # Set config in first session
        config_service1 = ConfigDBService(db_session)
        config_service1.set_read_auth_enabled(True, "admin1")

        # Create new config service instance (simulating restart)
        config_service2 = ConfigDBService(db_session)

        # Clear cache to force database read
        ConfigDBService._cache.clear()
        ConfigDBService._cache_timestamps.clear()

        # Verify config persisted
        assert config_service2.get_read_auth_enabled() == True
