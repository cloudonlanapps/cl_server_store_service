from store.db_service import EntitySchema, FaceSchema, FaceMatchSchema, KnownPersonSchema

def test_face_cascade(db_service):
    """Test standard cascade from Entity -> Face -> FaceMatch."""
    
    # 1. Create Entity
    entity = db_service.entity.create(EntitySchema(id=1, label="Test Entity"))
    
    # 2. Create Face
    face = db_service.face.create(FaceSchema(
        id=100, 
        entity_id=1, 
        bbox="[0,0,1,1]", 
        confidence=0.9, 
        landmarks="[]", 
        file_path="face.jpg",
        created_at=12345
    ))
    
    # 3. Create another Face and a Match
    face2 = db_service.face.create(FaceSchema(
        id=101, 
        entity_id=1, 
        bbox="[0,0,1,1]", 
        confidence=0.8, 
        landmarks="[]", 
        file_path="face2.jpg",
        created_at=12345
    ))
    
    match = db_service.face_match.create(FaceMatchSchema(
        face_id=100, 
        matched_face_id=101, 
        similarity_score=0.95, 
        created_at=12345
    ))
    
    # Verify creation
    assert db_service.face.get(100) is not None
    assert len(db_service.face_match.get_by_face_id(100)) == 1
    
    # 4. Delete Entity
    db_service.entity.delete(1)
    
    # 5. Verify Cascades
    assert db_service.face.get(100) is None
    assert db_service.face.get(101) is None
    assert len(db_service.face_match.get_by_face_id(100)) == 0  # Should be empty

def test_known_person_linking(db_service):
    """Test linking faces to KnownPerson."""
    
    # Setup
    entity = db_service.entity.create(EntitySchema(id=2, label="Entity 2"))
    face = db_service.face.create(FaceSchema(
        id=200, 
        entity_id=2, 
        bbox="[]", 
        confidence=0.9, 
        landmarks="[]", 
        file_path="f.jpg",
        created_at=1000
    ))
    
    # Create Person
    person = db_service.known_person.create_with_flush()
    assert person.id is not None
    
    # Link Face
    updated_face = db_service.face.update_known_person_id(200, person.id)
    assert updated_face.known_person_id == person.id
    
    # Verify lookup by person
    faces = db_service.face.get_by_known_person_id(person.id)
    assert len(faces) == 1
    assert faces[0].id == 200

def test_known_person_delete_prevention(db_service):
    """Test that KnownPerson cannot be deleted if faces are linked."""
    
    # Setup
    entity = db_service.entity.create(EntitySchema(id=3, label="Entity 3"))
    person = db_service.known_person.create_with_flush()
    face = db_service.face.create(FaceSchema(
        id=300, 
        entity_id=3, 
        bbox="[]", 
        confidence=0.9, 
        landmarks="[]", 
        file_path="f.jpg",
        created_at=1000,
        known_person_id=person.id
    ))
    
    # Try to delete Person -> Should raise ValueError
    import pytest
    with pytest.raises(ValueError, match="Face\(s\) are linked"):
        db_service.known_person.delete(person.id)
        
    # Unlink
    db_service.face.update_known_person_id(300, None)
    
    # Delete -> Should succeed
    assert db_service.known_person.delete(person.id) is True
