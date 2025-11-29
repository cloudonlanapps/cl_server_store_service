"""
Pytest configuration and fixtures for testing the CoLAN server.
"""

import os
import shutil
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Set up test environment variables BEFORE importing from src
# IMPORTANT: Always use a test-specific directory for CL_SERVER_DIR
# NEVER use the production CL_SERVER_DIR from environment
# This prevents tests from contaminating production data
test_dir = Path(__file__).parent
project_root = test_dir.parent
test_cl_server_dir = project_root.parent / "test_artifacts" / "cl_server"
test_cl_server_dir.mkdir(parents=True, exist_ok=True)

# Override CL_SERVER_DIR to ensure tests never touch production data
os.environ["CL_SERVER_DIR"] = str(test_cl_server_dir)

# Add tests directory to Python path for test_config import
sys.path.insert(0, str(Path(__file__).parent))

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from test_config import (
    IMAGES_DIR,
    TEST_IMAGES,
    TEST_DB_URL,
    get_all_test_images,
)


@pytest.fixture(scope="session")
def test_images_dir():
    """Path to test images directory (absolute path)."""
    return IMAGES_DIR


@pytest.fixture(scope="function")
def test_engine():
    """Create a test database engine with versioning support."""
    # Use in-memory SQLite with StaticPool for thread safety
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Import models and configure versioning BEFORE creating tables
    from src.models import Base
    from sqlalchemy.orm import configure_mappers

    # This must be called before create_all to ensure version tables are created
    configure_mappers()

    # Now create all tables including version tables
    Base.metadata.create_all(bind=engine)

    yield engine

    # Cleanup
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def test_db_session(test_engine):
    """Create a test database session."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_engine
    )
    session = TestingSessionLocal()

    yield session

    session.close()


@pytest.fixture(scope="function")
def client(test_engine, clean_media_dir):
    """Create a test client with a fresh database and test media directory."""
    # Create session maker
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_engine
    )

    # Override the get_db dependency
    def override_get_db():
        try:
            db = TestingSessionLocal()
            yield db
        finally:
            db.close()

    # Import app and override dependency
    from src import app
    from src.database import get_db
    from src.service import EntityService
    from src.auth import get_current_user_with_write_permission

    app.dependency_overrides[get_db] = override_get_db

    # Override auth dependency to bypass authentication in tests
    def override_auth():
        return {
            "sub": "testuser",
            "permissions": ["media_store_write"],
            "is_admin": True,
        }

    app.dependency_overrides[get_current_user_with_write_permission] = override_auth

    # Monkey patch EntityService to use test media directory
    original_init = EntityService.__init__

    def patched_init(self, db, base_dir=None):
        original_init(self, db, base_dir=str(clean_media_dir))

    EntityService.__init__ = patched_init

    # Create test client
    with TestClient(app) as test_client:
        yield test_client

    # Cleanup
    EntityService.__init__ = original_init
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def clean_media_dir():
    """Clean up media files directory before and after tests."""
    from test_config import TEST_MEDIA_DIR

    # Clean before test
    if TEST_MEDIA_DIR.exists():
        shutil.rmtree(TEST_MEDIA_DIR)
    TEST_MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    yield TEST_MEDIA_DIR

    # Clean after test
    if TEST_MEDIA_DIR.exists():
        shutil.rmtree(TEST_MEDIA_DIR)


@pytest.fixture
def sample_image(test_images_dir):
    """Get a sample image file for testing (absolute path)."""
    images = get_all_test_images()
    if not images:
        pytest.skip(
            f"No test images found. Please add images to {test_images_dir} or update test_files.txt"
        )
    return images[0]


@pytest.fixture
def sample_images(test_images_dir):
    """Get multiple sample images for testing (absolute paths)."""
    images = get_all_test_images()
    if len(images) < 2:
        pytest.skip(
            f"Not enough test images found. Please add at least 2 images to {test_images_dir} or update test_files.txt"
        )
    return images[:30]  # Return up to 30 images for pagination testing


@pytest.fixture
def file_storage_service(clean_media_dir):
    """Create a FileStorageService instance using the clean media directory."""
    from src.file_storage import FileStorageService

    return FileStorageService(base_dir=str(clean_media_dir))


@pytest.fixture(scope="function")
def key_pair(tmp_path):
    """Generate ES256 key pair for JWT testing.

    Returns:
        tuple: (private_key_pem, public_key_path) where:
            - private_key_pem: bytes of PEM-formatted private key
            - public_key_path: str path to temporary public key file
    """
    # Generate private key
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())

    # Serialize private key to PEM format
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    # Serialize public key to PEM format
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    # Save public key to temporary file
    public_key_path = tmp_path / "public_key.pem"
    public_key_path.write_bytes(public_pem)

    return private_pem, str(public_key_path)


@pytest.fixture(scope="function")
def jwt_token_generator(key_pair):
    """Generate JWT tokens with configurable claims for testing.

    Provides a TestTokenGenerator that can create valid, expired, or invalid tokens.
    """
    class TestTokenGenerator:
        """Helper class to generate JWT tokens for testing."""

        def __init__(self, private_key_pem):
            """Initialize with private key for signing tokens."""
            self.private_key = private_key_pem

        def generate_token(self, sub="testuser", permissions=None,
                          is_admin=False, expired=False):
            """Generate a JWT token with specified claims.

            Args:
                sub: Subject (username) claim
                permissions: List of permissions (e.g., ["media_store_write"])
                is_admin: Whether user is admin
                expired: If True, token is already expired

            Returns:
                str: JWT token string
            """
            if permissions is None:
                permissions = ["media_store_write"]

            # Calculate expiration
            if expired:
                exp = datetime.utcnow() - timedelta(hours=1)
            else:
                exp = datetime.utcnow() + timedelta(hours=1)

            payload = {
                "sub": sub,
                "permissions": permissions,
                "is_admin": is_admin,
                "exp": exp,
                "iat": datetime.utcnow(),
            }

            # Encode with ES256 algorithm
            token = jwt.encode(
                payload,
                self.private_key.decode() if isinstance(self.private_key, bytes) else self.private_key,
                algorithm="ES256"
            )
            return token

        def generate_invalid_token_wrong_key(self):
            """Generate a token signed with a different private key (invalid signature).

            Returns:
                str: JWT token signed with wrong key
            """
            # Generate a different key pair
            wrong_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
            wrong_key_pem = wrong_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )

            payload = {
                "sub": "testuser",
                "permissions": ["media_store_write"],
                "is_admin": False,
                "exp": datetime.utcnow() + timedelta(hours=1),
                "iat": datetime.utcnow(),
            }

            token = jwt.encode(
                payload,
                wrong_key_pem.decode(),
                algorithm="ES256"
            )
            return token

    return TestTokenGenerator(key_pair[0])


@pytest.fixture(scope="function")
def admin_token(jwt_token_generator):
    """Generate a valid admin token for testing.

    Returns:
        str: JWT token with admin permissions
    """
    return jwt_token_generator.generate_token(
        sub="admin_user",
        permissions=["media_store_read", "media_store_write"],
        is_admin=True
    )


@pytest.fixture(scope="function")
def write_token(jwt_token_generator):
    """Generate a valid write-only token for testing.

    Returns:
        str: JWT token with write permission only
    """
    return jwt_token_generator.generate_token(
        sub="write_user",
        permissions=["media_store_write"],
        is_admin=False
    )


@pytest.fixture(scope="function")
def read_token(jwt_token_generator):
    """Generate a valid read-only token for testing.

    Returns:
        str: JWT token with read permission only
    """
    return jwt_token_generator.generate_token(
        sub="read_user",
        permissions=["media_store_read"],
        is_admin=False
    )


@pytest.fixture(scope="function")
def auth_client(test_engine, clean_media_dir, key_pair, monkeypatch):
    """Create a test client WITHOUT auth override for testing authentication.

    This client does NOT bypass authentication, allowing proper testing of auth flows.
    Uses the key_pair fixture to set up proper JWT validation.
    """
    import sys

    # Set PUBLIC_KEY_PATH environment variable for JWT validation
    _, public_key_path = key_pair
    monkeypatch.setenv("PUBLIC_KEY_PATH", public_key_path)

    # Clear auth module's public key cache to force reload from new path
    if "src.auth" in sys.modules:
        auth_module = sys.modules["src.auth"]
        auth_module._public_key_cache = None
        auth_module._public_key_load_attempts = 0

    # Create session maker
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_engine
    )

    # Override the get_db dependency
    def override_get_db():
        try:
            db = TestingSessionLocal()
            yield db
        finally:
            db.close()

    # Import app
    from src import app
    from src.database import get_db
    from src.service import EntityService

    app.dependency_overrides[get_db] = override_get_db

    # Monkey patch EntityService to use test media directory
    original_init = EntityService.__init__

    def patched_init(self, db, base_dir=None):
        original_init(self, db, base_dir=str(clean_media_dir))

    EntityService.__init__ = patched_init

    # Create test client
    with TestClient(app) as test_client:
        yield test_client

    # Cleanup
    EntityService.__init__ = original_init
    app.dependency_overrides.clear()
