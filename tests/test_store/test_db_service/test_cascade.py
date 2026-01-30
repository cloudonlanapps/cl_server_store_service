from store.db_service import EntitySchema, EntityIntelligenceData
from store.db_service.models import EntityIntelligence
from sqlalchemy import text

def test_intelligence_cascade_deletion(db_service):
    """Verify that deleting an Entity also deletes its Intelligence data."""
    
    # 1. Create Entity
    entity = db_service.entity.create(EntitySchema(id=80, label="To Delete"))
    
    # 2. Add Intelligence Data
    db_service.intelligence.update_intelligence_data(
        80, 
        EntityIntelligenceData(last_updated=100, overall_status="processing")
    )
    
    # Verify both exist
    assert db_service.entity.get(80) is not None
    assert db_service.intelligence.get_intelligence_data(80) is not None
    
    # 3. Delete Entity using Service (which uses db_service.delete usually, but here we test DB constraint)
    # We use the lower level db_service.entity.delete() which performs a DB delete.
    # Note: The full EntityService.delete_entity logic is complex (soft delete first etc),
    # but the core requirement is that *if* the row is deleted, the sidecar is gone.
    
    db_service.entity.delete(80)
    
    # 4. Verify Entity is gone
    assert db_service.entity.get(80) is None
    
    # 5. Verify Intelligence is gone (Cascade check)
    intel = db_service.intelligence.get_intelligence_data(80)
    assert intel is None
    
    # Double check logical existence in DB directly to be sure it's not just the service returning None
    # Access internal session
    db = db_service.entity.db if db_service.entity.db else None
    if not db:
        from store.db_service import database
        db = database.SessionLocal()
        
    try:
        # Check raw table
        res = db.query(EntityIntelligence).filter(EntityIntelligence.entity_id == 80).first()
        assert res is None
    finally:
         if not db_service.entity.db:
             db.close()
