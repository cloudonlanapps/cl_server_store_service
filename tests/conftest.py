
import os
import shutil
import sys
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from jose import jwt
from pydantic import BaseModel
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Import test config and media files
from tests.test_config import (
    IMAGES_DIR,
    TEST_DATA_DIR,
    TEST_DB_URL,
    get_all_test_images,
)
from tests.test_media_files import get_test_media_files

# ============================================================================
# PYDANTIC MODELS
# ============================================================================


class IntegrationConfig(BaseModel):
    """Integration test configuration from CLI arguments."""

    auth_url: str
    compute_url: str
    qdrant_url: str
    username: str
    password: str


# ============================================================================
# PYTEST CONFIGURATION
# ============================================================================


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add CLI options for integration tests."""
    parser.addoption(
        "--auth-url",
        action="store",
        default=None,
        help="Auth service URL (required for integration tests)"
    )
    parser.addoption(
        "--compute-url",
        action="store",
        default=None,
        help="Compute service URL (required for integration tests)"
    )
    parser.addoption(
        "--qdrant-url",
        action="store",
        default=None,
        help="Qdrant service URL (required for integration tests)"
    )
    parser.addoption(
        "--username",
        action="store",
        default=None,
        help="Username for integration tests"
    )
    parser.addoption(
        "--password",
        action="store",
        default=None,
        help="Password for integration tests"
    )


# ============================================================================
# SESSION FIXTURES
# ============================================================================


@pytest.fixture(scope="session")
def integration_config(request: pytest.FixtureRequest) -> IntegrationConfig:
    """Parse CLI arguments into integration config.

    Fails if required options not provided.
    """
    auth_url = request.config.getoption("--auth-url")
    compute_url = request.config.getoption("--compute-url")
    qdrant_url = request.config.getoption("--qdrant-url")
    username = request.config.getoption("--username")
    password = request.config.getoption("--password")

    if not all([auth_url, compute_url, qdrant_url, username, password]):
        pytest.fail(
            "Integration tests require --auth-url, --compute-url, --qdrant-url, "
            "--username, and --password arguments"
        )

    return IntegrationConfig(
        auth_url=str(auth_url),
        compute_url=str(compute_url),
        qdrant_url=str(qdrant_url),
        username=str(username),
        password=str(password),
    )


# ============================================================================
# DATABASE FIXTURES
# ============================================================================


@pytest.fixture(scope="function")
def test_engine() -> Generator[Engine, None, None]:
    """Create a test database engine with versioning support."""
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    from sqlalchemy.orm import configure_mappers

    from store.common.models import Base

    configure_mappers()
    Base.metadata.create_all(bind=engine)

    yield engine

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def test_db_session(test_engine: Engine) -> Generator[Session, None, None]:
    """Create a test database session."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()

    yield session

    session.close()


# ============================================================================
# MEDIA DIRECTORY FIXTURES
# ============================================================================


@pytest.fixture(scope="function")
def clean_data_dir() -> Generator[Path, None, None]:
    """Clean up server data directory before and after tests."""
    if TEST_DATA_DIR.exists():
        shutil.rmtree(TEST_DATA_DIR)
    TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)

    yield TEST_DATA_DIR

    if TEST_DATA_DIR.exists():
        shutil.rmtree(TEST_DATA_DIR)


@pytest.fixture(scope="session")
def test_images_dir() -> Path:
    """Path to test images directory (absolute path)."""
    return IMAGES_DIR


@pytest.fixture
def sample_image(test_images_dir: Path) -> Path:
    """Get a sample image file for testing (absolute path)."""
    images = get_all_test_images()
    if not images:
        pytest.skip(
            f"No test images found. Please add images to {test_images_dir}"
        )
    return images[0]


@pytest.fixture
def sample_images(test_images_dir: Path) -> list[Path]:
    """Get multiple sample images for testing (absolute paths)."""
    images = get_all_test_images()
    if len(images) < 2:
        pytest.skip(
            f"Not enough test images found. Please add at least 2 images to {test_images_dir}"
        )
    return images[:30]


# ============================================================================
# CLIENT FIXTURES
# ============================================================================


@pytest.fixture(scope="function")
def client(
    test_engine: Engine,
    clean_data_dir: Path,
    integration_config: IntegrationConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    """Create a test client with REAL external services for integration tests."""
    from store.intelligence.logic.pysdk_config import PySDKRuntimeConfig

    # Configure PySDK to connect to real services
    pysdk_config = PySDKRuntimeConfig(
        auth_service_url=integration_config.auth_url,
        compute_service_url=integration_config.compute_url,
        qdrant_url=integration_config.qdrant_url,
        compute_username=integration_config.username,
        compute_password=integration_config.password,
    )

    monkeypatch.setenv("PYSDK_CONFIG_JSON", pysdk_config.model_dump_json())
    monkeypatch.setenv("CL_SERVER_DIR", str(clean_data_dir))

    # Create session maker
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    # Override the get_db dependency
    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    # Import app and override dependency
    from store.common.auth import UserPayload, get_current_user
    from store.common.database import get_db
    from store.store.store import app

    # Clear any cached auth keys
    if "store.common.auth" in sys.modules:
        sys.modules["store.common.auth"]._public_key_cache = None
        sys.modules["store.common.auth"]._public_key_load_attempts = 0

    app.dependency_overrides[get_db] = override_get_db

    # Override auth dependency to bypass authentication in tests
    def override_auth():
        return UserPayload(
            id="testuser",
            permissions=["media_store_write", "ai_inference_support"],
            is_admin=True,
        )

    app.dependency_overrides[get_current_user] = override_auth

    # Create test client - FastAPI lifespan will connect to REAL services
    
    from store.store.config import StoreConfig
    
    store_config = StoreConfig(
        cl_server_dir=clean_data_dir,

        media_storage_dir=clean_data_dir / "media",
        public_key_path=clean_data_dir / "keys" / "public_key.pem",
        auth_disabled=False,
    )
    app.state.config = store_config
    app.state.pysdk_config = pysdk_config

    with TestClient(app) as test_client:
        yield test_client

    # Cleanup
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def auth_client(
    test_engine: Engine,
    clean_data_dir: Path,
    integration_config: IntegrationConfig,
    key_pair: tuple[bytes, str],
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    """Create a test client WITHOUT auth override for testing authentication."""
    from store.intelligence.logic.pysdk_config import PySDKRuntimeConfig

    # Configure PySDK to connect to real services
    pysdk_config = PySDKRuntimeConfig(
        auth_service_url=integration_config.auth_url,
        compute_service_url=integration_config.compute_url,
        qdrant_url=integration_config.qdrant_url,
        compute_username=integration_config.username,
        compute_password=integration_config.password,
    )

    monkeypatch.setenv("PYSDK_CONFIG_JSON", pysdk_config.model_dump_json())
    monkeypatch.setenv("CL_SERVER_DIR", str(clean_data_dir))


    # Set up JWT key pair
    _, public_key_path = key_pair
    
    # Use clean_data_dir for key path
    expected_key_path = clean_data_dir / "keys" / "public_key.pem"
    expected_key_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(public_key_path, expected_key_path)
    
    # Create session maker
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    from store.common.auth import get_current_user
    from store.common.database import get_db
    from store.store.store import app

    # Clear cached auth keys
    if "store.common.auth" in sys.modules:
        sys.modules["store.common.auth"]._public_key_cache = None
        sys.modules["store.common.auth"]._public_key_load_attempts = 0

    # Clear any existing auth override
    if get_current_user in app.dependency_overrides:
        del app.dependency_overrides[get_current_user]

    app.dependency_overrides[get_db] = override_get_db

    # Create StoreConfig and set on app.state
    from store.store.config import StoreConfig
    
    store_config = StoreConfig(
        cl_server_dir=clean_data_dir,

        media_storage_dir=clean_data_dir / "media",
        public_key_path=clean_data_dir / "keys" / "public_key.pem",
        auth_disabled=False,
    )
    app.state.config = store_config
    app.state.pysdk_config = pysdk_config

    # Create test client - connects to REAL services
    with TestClient(app) as test_client:
        yield test_client

    # Cleanup
    if "store.common.auth" in sys.modules:
        sys.modules["store.common.auth"]._public_key_cache = None
        sys.modules["store.common.auth"]._public_key_load_attempts = 0

    app.dependency_overrides.clear()


# ============================================================================
# JWT FIXTURES
# ============================================================================


@pytest.fixture(scope="function")
def key_pair(tmp_path: Path) -> tuple[bytes, str]:
    """Generate ES256 key pair for JWT testing."""
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
def jwt_token_generator(key_pair: tuple[bytes, str]) -> Any:
    """Generate JWT tokens with configurable claims for testing."""

    class TestTokenGenerator:
        """Helper class to generate JWT tokens for testing."""

        private_key: bytes | str

        def __init__(self, private_key_pem: bytes) -> None:
            """Initialize with private key for signing tokens."""
            self.private_key = private_key_pem

        def generate_token(
            self,
            sub: str = "testuser",
            permissions: list[str] | None = None,
            is_admin: bool = False,
            expired: bool = False,
        ) -> str:
            """Generate a JWT token with specified claims."""
            if permissions is None:
                permissions = ["media_store_write"]

            # Calculate expiration
            if expired:
                exp = datetime.now(UTC) - timedelta(hours=1)
            else:
                exp = datetime.now(UTC) + timedelta(hours=1)

            payload: dict[str, str | list[str] | bool | datetime] = {
                "id": sub,
                "permissions": permissions,
                "is_admin": is_admin,
                "exp": exp,
                "iat": datetime.now(UTC),
            }

            # Encode with ES256 algorithm
            token: str = jwt.encode(
                payload,
                (
                    self.private_key.decode()
                    if isinstance(self.private_key, bytes)
                    else self.private_key
                ),
                algorithm="ES256",
            )
            return token

        def generate_invalid_token_wrong_key(self) -> str:
            """Generate a token signed with a different private key."""
            # Generate a different key pair
            wrong_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
            wrong_key_pem = wrong_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )

            payload: dict[str, str | list[str] | bool | datetime] = {
                "id": "testuser",
                "permissions": ["media_store_write"],
                "is_admin": False,
                "exp": datetime.now(UTC) + timedelta(hours=1),
                "iat": datetime.now(UTC),
            }

            token: str = jwt.encode(payload, wrong_key_pem.decode(), algorithm="ES256")
            return token

    return TestTokenGenerator(key_pair[0])


@pytest.fixture(scope="function")
def admin_token(jwt_token_generator: Any) -> str:
    """Generate a valid admin token for testing."""
    return jwt_token_generator.generate_token(
        sub="admin_user",
        permissions=["media_store_read", "media_store_write"],
        is_admin=True,
    )


@pytest.fixture(scope="function")
def write_token(jwt_token_generator: Any) -> str:
    """Generate a valid write-only token for testing."""
    return jwt_token_generator.generate_token(
        sub="write_user", permissions=["media_store_write"], is_admin=False
    )


@pytest.fixture(scope="function")
def read_token(jwt_token_generator: Any) -> str:
    """Generate a valid read-only token for testing."""
    return jwt_token_generator.generate_token(
        sub="read_user", permissions=["media_store_read"], is_admin=False
    )


@pytest.fixture(scope="function")
def inference_token(jwt_token_generator: Any) -> str:
    """Generate a token with ai_inference_support permission."""
    return jwt_token_generator.generate_token(
        sub="inference_user", permissions=["ai_inference_support"], is_admin=False
    )


@pytest.fixture(scope="function")
def inference_admin_token(jwt_token_generator: Any) -> str:
    """Generate an admin token with ai_inference_support permission."""
    return jwt_token_generator.generate_token(
        sub="inference_admin_user", permissions=["ai_inference_support"], is_admin=True
    )


# ============================================================================
# JOB AND STORAGE FIXTURES
# ============================================================================


@pytest.fixture
def sample_job_data() -> dict[str, Any]:
    """Sample job data for testing job endpoints."""
    return {
        "task_type": "image_processing",
        "priority": 5,
        "external_files": '[{"path": "/tmp/test_file.jpg", "metadata": {"name": "test_file.jpg"}}]',
    }


@pytest.fixture
def sample_job_data_with_external():
    """Sample job data with external files reference."""
    return {
        "task_type": "video_analysis",
        "priority": 3,
        "external_files": '[{"path": "/tmp/file1.mp4", "metadata": {"name": "file1.mp4"}}, {"path": "/tmp/file2.mp4", "metadata": {"name": "file2.mp4"}}]',
    }


@pytest.fixture
def sample_job_data_high_priority():
    """Sample high-priority job data."""
    return {
        "task_type": "transcoding",
        "priority": 10,
        "external_files": '[{"path": "/tmp/high_priority_file.mp4", "metadata": {"name": "high_priority_file.mp4"}}]',
    }


@pytest.fixture(scope="function")
def file_storage_service(clean_data_dir: Path) -> Any:
    """Create an EntityStorageService instance using the clean media directory."""
    from store.store.entity_storage import EntityStorageService

    return EntityStorageService(base_dir=str(clean_data_dir / "media"))


@pytest.fixture(scope="function")
def mock_compute_client(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Mock ComputeClient for testing job submission."""
    from unittest.mock import AsyncMock, MagicMock

    client = MagicMock()
    client.face_detection = MagicMock()
    client.face_detection.detect = AsyncMock()
    client.clip_embedding = MagicMock()
    client.clip_embedding.embed_image = AsyncMock()
    client.download_job_file = AsyncMock()
    client.close = AsyncMock()

    return client


@pytest.fixture(scope="function")
def mock_qdrant_store(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Mock QdrantImageStore for testing embedding operations."""
    from unittest.mock import MagicMock

    store = MagicMock()
    store.add_vector = MagicMock()
    store.get_vector = MagicMock(return_value=[])
    store.search = MagicMock(return_value=[])

    return store
