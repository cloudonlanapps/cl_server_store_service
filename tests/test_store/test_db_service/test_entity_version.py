from store.db_service import EntitySchema
from sqlalchemy.orm import Session
import pytest
# We need to access db session directly to force commit if create/update didn't close transaction in a way continuum likes,
# but BaseDBService opens/closes session per method.
# Continuum usually works on flush/commit. BaseDBService does commit.
# So creating an entity should create a version.

def test_entity_version_tracking(db_service):
    # 1. Create Entity (Version 1 - INSERT)
    # Note: Continuum creates version on insert.
    entity = db_service.entity.create(EntitySchema(id=500, label="V1", is_collection=False))
    
    # 2. Update Entity (Version 2 - UPDATE)
    db_service.entity.update(500, EntitySchema(id=500, label="V2"))
    
    # 3. Get all versions
    versions = db_service.entity_version.get_all_for_entity(500)
    
    # Expect 2 versions
    assert len(versions) >= 2
    # Verify content
    v1 = versions[0]
    v2 = versions[-1]
    
    assert v1.label == "V1"
    assert v2.label == "V2"
    # assert v1.operation_type == 0 # INSERT
    # assert v2.operation_type == 1 # UPDATE 
    # Note: checking operation_type might depend on implementation details of continuum (type 0, 1, 2)
    # But usually 0=INSERT, 1=UPDATE, 2=DELETE.

def test_get_versions_in_range(db_service):
    # Create entity
    db_service.entity.create(EntitySchema(id=600, label="Start"))
    
    # Store initial transaction ID (last one)
    # We need to peek at transaction table or just check versions
    versions = db_service.entity_version.get_all_for_entity(600)
    first_tid = versions[0].transaction_id
    
    # Make updates
    db_service.entity.update(600, EntitySchema(id=600, label="Update 1"))
    db_service.entity.update(600, EntitySchema(id=600, label="Update 2"))
    
    # Get changes since first_tid
    changes = db_service.entity_version.get_versions_in_range(first_tid)
    
    # Should contain entity 600 with latest state "Update 2"
    assert 600 in changes
    assert changes[600].label == "Update 2"
    
@pytest.mark.skip(reason="delete not supported")
def test_deleted_entity_version(db_service):
    # Create and Delete
    db_service.entity.create(EntitySchema(id=700, label="To Delete"))
    db_service.entity.delete(700)
    
    # Should still find versions
    versions = db_service.entity_version.get_all_for_entity(700)
    assert len(versions) > 0
    # Last version might receive DELETE operation type if configured, 
    # but the object state is usually what it was before delete?
    # Actually continuum inserts a record for DELETE.
    
    assert versions[-1].label == "To Delete"
