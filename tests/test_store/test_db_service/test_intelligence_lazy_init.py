from store.db_service import EntitySchema, EntityIntelligenceData
from store.db_service.intelligence import EntityIntelligenceDBService
from store.db_service.models import Entity
import pytest

from store.db_service import DBService, database
from sqlalchemy.orm import sessionmaker

@pytest.fixture
def db_service(test_engine, monkeypatch):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    monkeypatch.setattr(database, "SessionLocal", TestingSessionLocal)
    return DBService()

def test_atomic_update_lazy_creates_record(db_service):
    """Verify atomic_update_intelligence_data creates record if missing."""
    # 1. Create Entity without intelligence data
    entity_data = EntitySchema(
        id=500,
        label="Lazy Test",
        is_collection=False
    )
    db_service.entity.create(entity_data)
    
    # Verify no intelligence relation yet
    session = database.SessionLocal()
    try:
        # We need to query raw model to check relation
        ent = session.get(Entity, 500)
        assert ent.intelligence_rel is None
    finally:
        session.close()

    # 2. Call atomic update
    def update_fn(data):
        data.overall_status = "processing"
        
    result = db_service.intelligence.atomic_update_intelligence_data(500, update_fn)
    
    # 3. Verify it was created and updated
    assert result is not None
    assert result.overall_status == "processing"
    
    # Verify in DB
    session = database.SessionLocal()
    try:
        ent = session.get(Entity, 500)
        assert ent.intelligence_rel is not None
        # intelligence_data is stored as JSON (dict) in DB
        assert ent.intelligence_rel.intelligence_data["overall_status"] == "processing"
    finally:
        session.close()
