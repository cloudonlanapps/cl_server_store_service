from store.db_service import EntitySchema, EntityIntelligenceData, JobInfo, InferenceStatus
from store.db_service.db_internals import Entity

def test_intelligence_crud_via_service(db_service):
    """Test creating and updating intelligence data via EntityIntelligenceService."""
    # 1. Create Entity (without intelligence)
    entity_data = EntitySchema(
        id=50, 
        label="Img"
    )
    db_service.entity.create(entity_data)
    
    # 2. Add intelligence data via new service
    intel_init = EntityIntelligenceData(
        last_updated=1000,
        overall_status="queued"
    )
    
    # Update (creates sidecar record)
    result = db_service.intelligence.update_intelligence_data(50, intel_init)
    assert result is not None
    assert result.last_updated == 1000
    
    # 3. Verify retrieval
    retrieved = db_service.intelligence.get_intelligence_data(50)
    assert retrieved is not None
    assert retrieved.last_updated == 1000
    assert retrieved.overall_status == "queued"
    
    # Verify Entity retrieval does NOT contain intelligence data (implicit check)
    # EntitySchema no longer has intelligence_data field, so we can't check it directly
    # but strictly speaking, we just ensured it's stored.
    
    # 4. Simulate "Update Job IDs"
    current_data = retrieved
    new_job = JobInfo(job_id="job_123", task_type="face_detection", started_at=1001)
    
    # Append job
    current_data.active_jobs.append(new_job)
    current_data.last_updated = 1002
    current_data.inference_status.face_detection = "processing"
    
    # Update via update_intelligence_data
    updated = db_service.intelligence.update_intelligence_data(50, current_data)
    
    assert updated is not None
    assert len(updated.active_jobs) == 1
    assert updated.active_jobs[0].job_id == "job_123"
    assert updated.inference_status.face_detection == "processing"


def test_entity_job_lifecycle_simulation(db_service):
    """Test the lifecycle of a job as stored in intelligence_data."""
    # Create Entity
    db_service.entity.create(EntitySchema(id=60, label="Video"))
    
    # 1. Start Job (Queued/Processing)
    job_info = JobInfo(job_id="uuid-1", task_type="clip_embedding", started_at=2000)
    intel_data = EntityIntelligenceData(
        last_updated=2000,
        overall_status="processing",
        active_jobs=[job_info],
        inference_status=InferenceStatus(clip_embedding="processing")
    )
    
    db_service.intelligence.update_intelligence_data(60, intel_data)
    
    data1 = db_service.intelligence.get_intelligence_data(60)
    assert len(data1.active_jobs) == 1
    assert data1.inference_status.clip_embedding == "processing"
    
    # 2. Job Completes (Remove from active_jobs, update status)
    # Logic similar to JobSubmissionService.update_job_status
    current_intel = data1
    # Remove job
    current_intel.active_jobs = [j for j in current_intel.active_jobs if j.job_id != "uuid-1"]
    current_intel.inference_status.clip_embedding = "completed"
    current_intel.last_updated = 3000
    
    db_service.intelligence.update_intelligence_data(60, current_intel)
    
    data2 = db_service.intelligence.get_intelligence_data(60)
    assert len(data2.active_jobs) == 0
    assert data2.inference_status.clip_embedding == "completed"


def test_atomic_update(db_service):
    """Test atomic update using read-modify-write."""
    db_service.entity.create(EntitySchema(id=70, label="Atomic"))
    
    init_data = EntityIntelligenceData(last_updated=100, face_count=0)
    db_service.intelligence.update_intelligence_data(70, init_data)
    
    def update_fn(data):
        data.face_count += 5
        data.last_updated = 200
        
    updated = db_service.intelligence.atomic_update_intelligence_data(70, update_fn)
    
    assert updated.face_count == 5
    # Service automatically updates timestamp, so it will be > 100 (initial) and not necessarily 200
    assert updated.last_updated > 100
    
    # Verify persistence
    stored = db_service.intelligence.get_intelligence_data(70)
    assert stored.face_count == 5


def test_missing_entity_prevention(db_service):
    """Test updating intelligence for non-existent entity."""
    intel = EntityIntelligenceData(last_updated=0, overall_status="new")
    
    # update_intelligence_data returns None if not found
    res = db_service.intelligence.update_intelligence_data(999, intel)
    assert res is None
