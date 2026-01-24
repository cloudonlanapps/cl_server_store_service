
def test_retrieval_service_init():
    from store.m_insight.retrieval_service import IntelligenceRetrieveService
    from store.store.config import StoreConfig
    from unittest.mock import MagicMock
    
    config = MagicMock(spec=StoreConfig)
    config.qdrant_url = "http://localhost:6333"
    config.qdrant_collection = "clip"
    config.face_collection = "face"
    config.dino_collection = "dino"
    config.face_vector_size = 512
    
    # Mock vector store factories to avoid real connection
    with (
        MagicMock() as mock_clip, 
        MagicMock() as mock_face, 
        MagicMock() as mock_dino
    ):
        # We need to patch the get_*_store functions
        import store.m_insight.retrieval_service as rs
        rs.get_clip_store = MagicMock(return_value=mock_clip)
        rs.get_face_store = MagicMock(return_value=mock_face)
        rs.get_dino_store = MagicMock(return_value=mock_dino)
        
        service = IntelligenceRetrieveService(config)
        assert service.db is not None
        assert service.qdrant_store == mock_clip
