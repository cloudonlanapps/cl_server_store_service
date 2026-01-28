from store.db_service import EntitySchema, EntityIntelligenceData, JobInfo, InferenceStatus
from store.db_service.db_internals import Entity

def test_intelligence_crud_via_entity(db_service):
    """Test creating and updating intelligence data via Entity service."""
    # 1. Create Entity with initial intelligence
    intel_init = EntityIntelligenceData(
        last_updated=1000,
        overall_status="queued"
    )
    entity_data = EntitySchema(
        id=50, 
        label="Img", 
        intelligence_data=intel_init
    )
    db_service.entity.create(entity_data)
    
    # Verify creation
    retrieved = db_service.entity.get(50)
    assert retrieved is not None
    assert retrieved.intelligence_data.last_updated == 1000
    assert retrieved.intelligence_data.overall_status == "queued"
    
    # 2. Simulate "Update Job IDs" (feature test)
    # The feature was: adding a job ID.
    # New way: Add to active_jobs list.
    
    current_data = retrieved.intelligence_data
    new_job = JobInfo(job_id="job_123", task_type="face_detection", started_at=1001)
    
    # Append job
    current_data.active_jobs.append(new_job)
    current_data.last_updated = 1002
    current_data.inference_status.face_detection = "processing"
    
    # Update via update_intelligence_data
    updated = db_service.entity.update_intelligence_data(50, current_data)
    
    assert updated is not None
    assert len(updated.intelligence_data.active_jobs) == 1
    assert updated.intelligence_data.active_jobs[0].job_id == "job_123"
    assert updated.intelligence_data.inference_status.face_detection == "processing"


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
    
    db_service.entity.update_intelligence_data(60, intel_data)
    
    e1 = db_service.entity.get(60)
    assert len(e1.intelligence_data.active_jobs) == 1
    assert e1.intelligence_data.inference_status.clip_embedding == "processing"
    
    # 2. Job Completes (Remove from active_jobs, update status)
    # Logic similar to JobSubmissionService.update_job_status
    current_intel = e1.intelligence_data
    # Remove job
    current_intel.active_jobs = [j for j in current_intel.active_jobs if j.job_id != "uuid-1"]
    current_intel.inference_status.clip_embedding = "completed"
    current_intel.last_updated = 3000
    
    db_service.entity.update_intelligence_data(60, current_intel)
    
    e2 = db_service.entity.get(60)
    assert len(e2.intelligence_data.active_jobs) == 0
    assert e2.intelligence_data.inference_status.clip_embedding == "completed"


def test_missing_entity_prevention(db_service):
    """Test updating intelligence for non-existent entity."""
    intel = EntityIntelligenceData(last_updated=0, overall_status="new")
    
    # Should check return value or raise?
    # update_intelligence_data returns None if not found
    res = db_service.entity.update_intelligence_data(999, intel)
    assert res is None
