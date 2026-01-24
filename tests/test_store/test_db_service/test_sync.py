import pytest
from store.db_service import EntitySyncStateSchema

def test_sync_state_singleton(db_service):
    # 1. Get or Create
    state = db_service.sync_state.get_or_create()
    assert state.id == 1
    assert state.last_version == 0
    
    # 2. Update
    updated = db_service.sync_state.update_last_version(100)
    assert updated.last_version == 100
    
    # 3. Get again
    state2 = db_service.sync_state.get_or_create()
    assert state2.id == 1
    assert state2.last_version == 100
    
    # 4. Verify shorthand
    assert db_service.sync_state.get_last_version() == 100

def test_sync_state_restrictions(db_service):
    # Cannot create manually (raises NotImplementedError)
    with pytest.raises(NotImplementedError):
        db_service.sync_state.create(EntitySyncStateSchema())
        
    # Cannot delete
    with pytest.raises(NotImplementedError):
        db_service.sync_state.delete(1)
