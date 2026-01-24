import pytest
from store.common.config import BaseConfig
from store.db_service import DBService
from store.db_service.db_internals import Base

@pytest.fixture(scope="module")
def db_engine():
    # Use in-memory SQLite for tests
    from store.db_service import database
    # Reset globals to ensure clean state
    database.engine = database.create_db_engine("sqlite:///:memory:", echo=False)
    database.SessionLocal = database.create_session_factory(database.engine)
    
    # Create tables
    from sqlalchemy.orm import configure_mappers
    configure_mappers()
    Base.metadata.create_all(bind=database.engine)
    
    yield database.engine
    
    # Cleanup
    Base.metadata.drop_all(bind=database.engine)

@pytest.fixture
def store_config(tmp_path):
    # Mock config
    config = BaseConfig(
        cl_server_dir=tmp_path,
        media_storage_dir=tmp_path / "media",
        public_key_path=tmp_path / "keys" / "public_key.pem"
    )
    return config

@pytest.fixture
def db_service(db_engine):
    return DBService()
