"""
Authentication unit tests for media_store service.

These tests verify the authentication logic directly without going through
the full FastAPI request cycle. For full end-to-end testing, integration
tests with a running authentication service are recommended.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException


class TestAuthenticationLogic:
    """Test authentication logic functions directly."""

    @pytest.fixture(scope="class")
    def key_pair(self, tmp_path_factory):
        """Generate ES256 key pair for testing."""
        tmp_path = tmp_path_factory.mktemp("keys")

        # Generate private key
        private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())

        # Serialize keys
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        # Save public key
        public_key_path = tmp_path / "public_key.pem"
        public_key_path.write_bytes(public_pem)

        return private_pem, str(public_key_path)

    def _create_mock_request(self, no_auth=False):
        """Create a mock request with configured app state."""
        request = MagicMock()
        config = MagicMock()
        config.no_auth = no_auth
        request.app.state.config = config
        return request

    def test_require_permission_allows_correct_permission(self):
        """User with the required permission should be allowed."""
        from store.common.auth import UserPayload, require_permission

        # Mock user with write permission
        user = UserPayload(
            id="testuser",
            permissions=["media_store_write"],
            is_admin=False,
        )

        request = self._create_mock_request(no_auth=False)
        permission_checker = require_permission("media_store_write")
        
        result = asyncio.run(permission_checker(request, user))
        assert result == user

    def test_require_permission_allows_admin(self):
        """Admin user should be allowed even without specific permission."""
        from store.common.auth import UserPayload, require_permission

        user = UserPayload(id="admin", permissions=[], is_admin=True)

        request = self._create_mock_request(no_auth=False)
        permission_checker = require_permission("media_store_write")
        
        result = asyncio.run(permission_checker(request, user))
        assert result == user

    def test_require_permission_rejects_wrong_permission(self):
        """User with only read permission should be rejected when write is required."""
        from store.common.auth import UserPayload, require_permission

        user = UserPayload(
            id="testuser",
            permissions=["media_store_read"],
            is_admin=False,
        )

        request = self._create_mock_request(no_auth=False)
        
        with pytest.raises(HTTPException) as exc_info:
            permission_checker = require_permission("media_store_write")
            asyncio.run(permission_checker(request, user))

        assert exc_info.value.status_code == 403

    def test_require_permission_rejects_none_user(self):
        """None user (no auth) should be rejected when auth is not disabled."""
        from store.common.auth import require_permission

        request = self._create_mock_request(no_auth=False)
        
        with pytest.raises(HTTPException) as exc_info:
            permission_checker = require_permission("media_store_write")
            asyncio.run(permission_checker(request, None))

        assert exc_info.value.status_code == 401

    def test_require_permission_allows_read_permission(self):
        """User with media_store_read permission should be allowed."""
        from unittest.mock import MagicMock, patch

        from store.common.auth import UserPayload, require_permission

        user = UserPayload(
            id="testuser",
            permissions=["media_store_read"],
            is_admin=False,
        )

        request = self._create_mock_request(no_auth=False)

        # Mock ConfigService to return True for read_auth_enabled
        # This ensures the permission check proceeds normally
        with patch("store.store.config_service.ConfigService") as mock_config_service_class:
            mock_config_service = MagicMock()
            mock_config_service.get_read_auth_enabled.return_value = True
            mock_config_service_class.return_value = mock_config_service

            permission_checker = require_permission("media_store_read")
            result = asyncio.run(permission_checker(request, user))
            assert result == user

    def test_require_admin_allows_admin_user(self):
        """Admin user should be allowed by require_admin."""
        from store.common.auth import UserPayload, require_admin

        user = UserPayload(id="admin", permissions=[], is_admin=True)
        request = self._create_mock_request(no_auth=False)

        result = asyncio.run(require_admin(request, user))
        assert result == user

    def test_require_admin_rejects_non_admin(self):
        """Non-admin user should be rejected by require_admin."""
        from store.common.auth import UserPayload, require_admin

        user = UserPayload(
            id="testuser",
            permissions=["media_store_write"],
            is_admin=False,
        )
        request = self._create_mock_request(no_auth=False)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(require_admin(request, user))

        assert exc_info.value.status_code == 403


class TestAuthenticationModes:
    """Test authentication mode configurations."""

    def test_demo_mode_bypasses_permission_check(self):
        """When no_auth=true, permission checks should be bypassed."""
        from store.common.auth import require_permission

        # Mock request with no_auth=True
        request = MagicMock()
        config = MagicMock()
        config.no_auth = True
        request.app.state.config = config

        permission_checker = require_permission("media_store_write")
        result = asyncio.run(permission_checker(request, None))
        assert result is None

    def test_demo_mode_bypasses_admin_check(self):
        """When no_auth=true, admin checks should be bypassed."""
        from store.common.auth import require_admin

        # Mock request with no_auth=True
        request = MagicMock()
        config = MagicMock()
        config.no_auth = True
        request.app.state.config = config

        result = asyncio.run(require_admin(request, None))
        assert result is None


class TestJWTValidation:
    """Test JWT token validation via FastAPI TestClient.

    Tests validate tokens through actual HTTP requests to the API,
    ensuring the full dependency injection chain and authentication flow works.
    """

    def test_valid_token_is_decoded(
        self, auth_client, jwt_token_generator, key_pair
    ):
        """Valid JWT token should be decoded successfully."""
        # Note: auth_client fixture already sets up the correct public key path
        # matching key_pair, and creates StoreConfig accordingly.
        
        token = jwt_token_generator.generate_token(
            sub="testuser",
            permissions=["media_store_read"],
            is_admin=False,
            expired=False,
        )

        headers = {"Authorization": f"Bearer {token}"}
        response = auth_client.get("/entities/", headers=headers)

        # Token should be decoded successfully
        # Response should NOT be 401 (unauthorized)
        assert (
            response.status_code != 401
        ), f"Token validation failed: {response.json()}"
        # Should be 200 (success) or 400 (validation error), not 401 (auth error)
        assert response.status_code in [200, 400]

    def test_expired_token_is_rejected(
        self, auth_client, jwt_token_generator
    ):
        """Expired JWT token should be rejected with 401."""
        token = jwt_token_generator.generate_token(
            sub="testuser",
            permissions=["media_store_write"],
            is_admin=False,
            expired=True,  # Token is expired
        )

        headers = {"Authorization": f"Bearer {token}"}
        response = auth_client.get("/entities/", headers=headers)

        # Expired token should be rejected with 401
        assert response.status_code == 401
        assert "expired" in response.json().get("detail", "").lower()

    def test_invalid_token_format_is_rejected(
        self, auth_client, jwt_token_generator
    ):
        """Malformed tokens and tokens with wrong signatures should be rejected."""
        # Create multiple invalid tokens to test
        invalid_tokens = [
            "not.a.valid.token",  # Wrong format (too few parts)
            "invalid_format",  # Not JWT format at all
            "a.b",  # Missing signature part
            "!!!.!!!.!!!",  # Invalid base64
            jwt_token_generator.generate_invalid_token_wrong_key(),  # Valid format but wrong signature
        ]

        for invalid_token in invalid_tokens:
            headers = {"Authorization": f"Bearer {invalid_token}"}
            response = auth_client.get("/entities/", headers=headers)

            # All invalid tokens should return 401
            assert (
                response.status_code == 401
            ), f"Token '{invalid_token[:20]}...' should be rejected but got {response.status_code}"
