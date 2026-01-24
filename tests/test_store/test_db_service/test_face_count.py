from store.db_service import EntitySchema, FaceSchema, KnownPersonSchema
from cl_ml_tools import BBox, FaceLandmarks

def test_known_person_face_count(db_service):
    """Test face_count population in KnownPersonDBService."""
    
    # Setup: 1 Entity, 1 Person, 2 Faces linked
    entity = db_service.entity.create(EntitySchema(id=4, label="Entity 4"))
    person = db_service.known_person.create_with_flush()
    
    # 2 linked faces
    db_service.face.create(FaceSchema(
        id=400, entity_id=4, bbox=BBox(x1=0, y1=0, x2=1, y2=1), 
        confidence=0.9, landmarks=FaceLandmarks(
            right_eye=(0,0), left_eye=(0,0), nose_tip=(0,0), mouth_right=(0,0), mouth_left=(0,0)
        ), 
        file_path="f1.jpg", created_at=1000, known_person_id=person.id
    ))
    db_service.face.create(FaceSchema(
        id=401, entity_id=4, bbox=BBox(x1=0, y1=0, x2=1, y2=1), 
        confidence=0.9, landmarks=FaceLandmarks(
            right_eye=(0,0), left_eye=(0,0), nose_tip=(0,0), mouth_right=(0,0), mouth_left=(0,0)
        ), 
        file_path="f2.jpg", created_at=1000, known_person_id=person.id
    ))
    
    # 1 unlinked face
    db_service.face.create(FaceSchema(
        id=402, entity_id=4, bbox=BBox(x1=0, y1=0, x2=1, y2=1), 
        confidence=0.9, landmarks=FaceLandmarks(
            right_eye=(0,0), left_eye=(0,0), nose_tip=(0,0), mouth_right=(0,0), mouth_left=(0,0)
        ), 
        file_path="f3.jpg", created_at=1000, known_person_id=None
    ))
    
    # Verify get()
    retrieved = db_service.known_person.get(person.id)
    assert retrieved.face_count == 2
    
    # Verify get_all()
    all_persons = db_service.known_person.get_all()
    target_person = next((p for p in all_persons if p.id == person.id), None)
    assert target_person is not None
    assert target_person.face_count == 2
    
    # Verify update_name()
    updated = db_service.known_person.update_name(person.id, "Test Name")
    assert updated.face_count == 2
    
    # Verify create_with_flush
    new_person = db_service.known_person.create_with_flush()
    assert new_person.face_count == 0  # Should be 0 initially
