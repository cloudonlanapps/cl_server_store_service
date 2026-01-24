from store.db_service import EntitySchema, FaceSchema
from cl_ml_tools import BBox, FaceLandmarks
import json

def test_face_serialization_explicit(db_service):
    """Explicitly test that BBox/Landmarks are stored as JSON strings and parsed back."""
    from store.db_service.models import Face
    from store.db_service import database
    
    # Create entity
    db_service.entity.create(EntitySchema(id=999, label="Serialization Test"))
    
    # Create face with complex types
    bbox = BBox(x1=0.1, y1=0.2, x2=0.3, y2=0.4)
    landmarks = FaceLandmarks(
        right_eye=(0.1,0.1), left_eye=(0.2,0.2), nose_tip=(0.3,0.3), 
        mouth_right=(0.4,0.4), mouth_left=(0.5,0.5)
    )
    
    # Test Create
    db_service.face.create(FaceSchema(
        id=900,
        entity_id=999,
        bbox=bbox,
        confidence=0.99,
        landmarks=landmarks,
        file_path="s.jpg",
        created_at=1000
    ))
    
    # 1. Verify RAW storage (Packing)
    # Open a raw session to bypass Pydantic conversion
    db = database.SessionLocal()
    try:
        raw_face = db.query(Face).filter(Face.id == 900).first()
        assert raw_face is not None
        
        # Verify columns are strings
        assert isinstance(raw_face.bbox, str)
        assert isinstance(raw_face.landmarks, str)
        
        # Verify content is valid JSON matching input
        bbox_dict = json.loads(raw_face.bbox)
        assert bbox_dict['x1'] == 0.1
        
        landmarks_dict = json.loads(raw_face.landmarks)
        assert landmarks_dict['right_eye'] == [0.1, 0.1] # Lists in JSON
    finally:
        db.close()
        
    # 2. Verify Schema parsing (Parsing)
    face_schema = db_service.face.get(900)
    assert isinstance(face_schema.bbox, BBox)
    assert face_schema.bbox.x1 == 0.1
    
    assert isinstance(face_schema.landmarks, FaceLandmarks)
    # Tuple conversion check works because we compare values
    # Pydantic model might convert back to tuple if defined as tuple in schema (FaceLandmarks definition)
    assert face_schema.landmarks.right_eye == (0.1, 0.1) 
