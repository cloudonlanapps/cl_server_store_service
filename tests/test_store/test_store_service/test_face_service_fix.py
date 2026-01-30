from unittest.mock import MagicMock
from store.db_service import EntitySchema, EntityIntelligenceData
from store.db_service.intelligence import EntityIntelligenceDBService
from store.db_service.db_internals import Face, Entity
from store.db_service import DBService
from store.db_service import database
from sqlalchemy.orm import sessionmaker
import pytest

@pytest.fixture
def db_service(test_engine, monkeypatch):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    monkeypatch.setattr(database, "SessionLocal", TestingSessionLocal)
    return DBService()

def test_face_deletion_decrements_count(db_service):
    """Verify that deleting a face decrements the face_count via EntityIntelligenceDBService."""
    
    import random
    uid = random.randint(1000, 9999)
    
    # 1. Create Entity with initial face count
    entity = db_service.entity.create(EntitySchema(id=uid, label="Face Test"))
    
    init_data = EntityIntelligenceData(last_updated=100, face_count=2)
    db_service.intelligence.update_intelligence_data(uid, init_data)
    
    # 2. Create Face record
    # We need to manually add a face to DB as FaceDBService might not be fully wired in this test scope
    # or we can use the raw DB session.
    
    db = db_service.entity.db
    should_close = False
    if db is None:
        from store.db_service import database
        db = database.SessionLocal()
        should_close = True
        
    # FORCE SYNC: Ensure the test session sees the data committed by db_service.entity.create
    # creating a new session usually sees committed data. 
    # But 'db' here comes from fixture, started BEFORE create() was called.
    # So we might need to commit/rollback to refresh.
    db.commit() 
    
    # Debug verification
    found = db.query(Entity).filter(Entity.id == uid).first()
    if not found:
        raise RuntimeError(f"Entity {uid} not visible in test session!")
        
    try:
        # Face model in SQL doesn't store embedding (it's in Vector DB)
        face = Face(
            entity_id=uid, 
            file_path="face.jpg",
            bbox="[0,0,1,1]",
            confidence=0.9,
            landmarks="[]",
            created_at=1000
        )
        db.add(face)
        db.commit()
        db.refresh(face)
        face_id = face.id
    finally:
        if should_close:
            # We keep it open if we need to pass it to FaceService, 
            # BUT FaceService expects a session.
            # If we close it, FaceService might fail if it tries to use it? 
            # Actually FaceService takes 'db' as arg.
            pass
    
    # 3. Initialize FaceService with real DBService but mock external stores
    from store.store.face_service import FaceService
    
    mock_storage = MagicMock()
    mock_vector = MagicMock()
    
    face_service = FaceService(
        db=db,
        db_service=db_service,
        face_store=mock_vector,
        storage_service=mock_storage
    )
    
    # 4. Perform Delete
    result = face_service.delete_face(face_id)
    
    assert result is True
    
    # 5. Verify Intelligence Data Update
    updated_data = db_service.intelligence.get_intelligence_data(uid)
    assert updated_data.face_count == 1
    
    # 6. Verify Face is gone
    deleted_face = db.query(Face).filter(Face.id == face_id).first()
    assert deleted_face is None
