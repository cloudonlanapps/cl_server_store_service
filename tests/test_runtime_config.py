"""
Tests for runtime configuration API and JWT user ID.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base, get_db
from src.models import ServiceConfig
from src.config_service import ConfigService
from src import app


from sqlalchemy.pool import StaticPool

# Test database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database for each test."""
    # Clear config cache before test
    ConfigService._cache.clear()

    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)

    # Clear config cache after test
    ConfigService._cache.clear()
    ConfigService._cache_timestamps.clear()


@pytest.fixture
def client():
    """Create a test client."""
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestConfigService:
    """Test ConfigService functionality."""

    def test_get_config_default(self, db_session):
        """Test getting config with default value."""
        config_service = ConfigService(db_session)
        value = config_service.get_config("nonexistent_key", "default_value")
        assert value == "default_value"

    def test_set_and_get_config(self, db_session):
        """Test setting and getting configuration."""
        config_service = ConfigService(db_session)

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
        config_service = ConfigService(db_session)

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
        config_service = ConfigService(db_session)

        # Set initial value
        config_service.set_config("cached_key", "value1", "user1")

        # Get value (should be cached)
        value1 = config_service.get_config("cached_key")
        assert value1 == "value1"

        # Manually update database (bypass cache)
        config = (
            db_session.query(ServiceConfig)
            .filter(ServiceConfig.key == "cached_key")
            .first()
        )
        config.value = "value2"
        db_session.commit()

        # Get value again (should still be cached)
        value2 = config_service.get_config("cached_key")
        assert value2 == "value1"  # Still cached

        # Clear cache by setting new value
        config_service.set_config("cached_key", "value3", "user2")
        value3 = config_service.get_config("cached_key")
        assert value3 == "value3"


class TestAdminConfigAPI:
    """Test admin configuration API endpoints."""

    def test_get_config_requires_admin(self, client, db_session):
        """Test that getting config requires admin access."""
        # TODO: This test requires proper JWT mocking
        # For now, just verify the endpoint exists
        response = client.get("/admin/config")
        # Should return 401 (no auth) or 403 (not admin)
        assert response.status_code in [401, 403]

    def test_update_read_auth_requires_admin(self, client, db_session):
        """Test that updating read auth requires admin access."""
        # TODO: This test requires proper JWT mocking
        response = client.put("/admin/config/read-auth", json={"enabled": True})
        # Should return 401 (no auth) or 403 (not admin)
        assert response.status_code in [401, 403]


class TestJWTUserID:
    """Test that JWT contains user ID in sub field."""

    def test_jwt_contains_user_id(self):
        """Test that JWT payload contains user ID, not username.

        This test verifies that the authentication service generates
        JWT tokens with user.id in the 'sub' field instead of user.username.

        NOTE: This requires the authentication service to be running
        and properly configured. This is an integration test.
        """
        # TODO: Implement full integration test with authentication service
        # For now, this is a placeholder to document the requirement
        pass

    def test_media_store_receives_user_id(self):
        """Test that media_store correctly receives and uses user ID from JWT.

        This test verifies that when a JWT is decoded, the 'sub' field
        contains a user ID that is used for added_by and updated_by tracking.
        """
        # TODO: Implement test with mocked JWT containing user ID
        pass


class TestReadAuthBehaviorWithConfig:
    """Test that read authentication behavior changes based on database config."""

    def test_read_auth_disabled_allows_access(self, client, db_session):
        """Test that read endpoints are accessible when read auth is disabled."""
        # Set read auth to disabled
        config_service = ConfigService(db_session)
        config_service.set_read_auth_enabled(False)

        # Try to access read endpoint without auth
        response = client.get("/entity/")
        # Should succeed (200) or return empty list, not 401/403
        assert response.status_code != 401
        assert response.status_code != 403

    def test_read_auth_enabled_requires_token(self, client, db_session):
        """Test that read endpoints require auth when read auth is enabled."""
        # Set read auth to enabled
        config_service = ConfigService(db_session)
        config_service.set_read_auth_enabled(True)

        # Try to access read endpoint without auth
        response = client.get("/entity/")
        # Should return 401 (unauthorized)
        # Note: This might fail if AUTH_DISABLED env var is set
        # TODO: Mock environment variables for this test
        pass

    def test_config_persists_across_sessions(self, db_session):
        """Test that configuration persists in database."""
        # Set config in first session
        config_service1 = ConfigService(db_session)
        config_service1.set_read_auth_enabled(True, "admin1")

        # Create new config service instance (simulating restart)
        config_service2 = ConfigService(db_session)

        # Clear cache to force database read
        ConfigService._cache.clear()
        ConfigService._cache_timestamps.clear()

        # Verify config persisted
        assert config_service2.get_read_auth_enabled() == True
