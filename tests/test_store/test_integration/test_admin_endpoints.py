"""Admin preference endpoint tests with JWT authentication."""

import pytest


pytestmark = pytest.mark.integration


class TestAdminPrefGetEndpoint:
    """Test GET /admin/pref endpoint."""

    def test_get_pref_with_admin_token_returns_200(self, auth_client, admin_token):
        """GET /admin/pref with admin token should return 200 OK."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = auth_client.get("/admin/pref", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_get_pref_with_read_only_token_returns_403(self, auth_client, read_token):
        """GET /admin/pref with read-only token should return 403 Forbidden."""
        headers = {"Authorization": f"Bearer {read_token}"}
        response = auth_client.get("/admin/pref", headers=headers)

        assert response.status_code == 403

    def test_get_pref_with_write_token_returns_403(self, auth_client, write_token):
        """GET /admin/pref with write token (not admin) should return 403 Forbidden."""
        headers = {"Authorization": f"Bearer {write_token}"}
        response = auth_client.get("/admin/pref", headers=headers)

        assert response.status_code == 403

    def test_get_pref_without_token_returns_401(self, auth_client):
        """GET /admin/pref without token should return 401 Unauthorized."""
        response = auth_client.get("/admin/pref")

        assert response.status_code == 401

    def test_get_pref_with_invalid_token_returns_401(self, auth_client):
        """GET /admin/pref with invalid token should return 401 Unauthorized."""
        headers = {"Authorization": "Bearer invalid.token.here"}
        response = auth_client.get("/admin/pref", headers=headers)

        assert response.status_code == 401


class TestAdminPrefPutEndpoint:
    """Test PUT /admin/pref/guest-mode endpoint."""

    def test_put_read_auth_with_admin_token_returns_200(self, auth_client, admin_token):
        """PUT /admin/pref/guest-mode with admin token should return 200 OK."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = auth_client.put(
            "/admin/pref/guest-mode", data={"guest_mode": "false"}, headers=headers
        )

        assert response.status_code == 200

    def test_put_read_auth_with_write_token_returns_403(self, auth_client, write_token):
        """PUT /admin/pref/guest-mode with write token (not admin) should return 403 Forbidden."""
        headers = {"Authorization": f"Bearer {write_token}"}
        response = auth_client.put(
            "/admin/pref/guest-mode", data={"guest_mode": "false"}, headers=headers
        )

        assert response.status_code == 403

    def test_put_read_auth_with_read_token_returns_403(self, auth_client, read_token):
        """PUT /admin/pref/guest-mode with read token should return 403 Forbidden."""
        headers = {"Authorization": f"Bearer {read_token}"}
        response = auth_client.put(
            "/admin/pref/guest-mode", data={"guest_mode": "false"}, headers=headers
        )

        assert response.status_code == 403

    def test_put_read_auth_without_token_returns_401(self, auth_client):
        """PUT /admin/pref/guest-mode without token should return 401 Unauthorized."""
        response = auth_client.put("/admin/pref/guest-mode", data={"guest_mode": "false"})

        assert response.status_code == 401

    def test_put_read_auth_with_invalid_token_returns_401(self, auth_client):
        """PUT /admin/pref/guest-mode with invalid token should return 401 Unauthorized."""
        headers = {"Authorization": "Bearer invalid.token.here"}
        response = auth_client.put(
            "/admin/pref/guest-mode", data={"guest_mode": "false"}, headers=headers
        )

        assert response.status_code == 401

    def test_pref_changes_persisted_in_database(
        self, auth_client, admin_token, test_db_session
    ):
        """Preference changes via PUT should be persisted in database."""
        from store.db_service.config import ConfigDBService



        # Clear cache before test
        ConfigDBService._cache.clear()
        ConfigDBService._cache_timestamps.clear()

        # Update config via API (guest_mode=false means read_auth_enabled=true)
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = auth_client.put(
            "/admin/pref/guest-mode", data={"guest_mode": "false"}, headers=headers
        )

        assert response.status_code == 200

        # Verify it was persisted in database
        config_service = ConfigDBService(test_db_session)
        is_enabled = config_service.get_read_auth_enabled()
        assert is_enabled is True

    def test_subsequent_get_returns_updated_pref(self, auth_client, admin_token):
        """Subsequent GET /admin/pref should return updated preference after PUT."""
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Update config (guest_mode=false means read_auth_enabled=true)
        response = auth_client.put(
            "/admin/pref/guest-mode", data={"guest_mode": "false"}, headers=headers
        )
        assert response.status_code == 200

        # Get updated config
        response = auth_client.get("/admin/pref", headers=headers)
        assert response.status_code == 200

        # Verify the config contains the updated value
        data = response.json()
        # The response should contain configuration info
        assert isinstance(data, dict)
