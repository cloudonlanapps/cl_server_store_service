
def test_schema_propagation():
    from store.m_insight import schemas
    # Verify EntityJobSchema is NOT in m_insight.schemas anymore (it was removed)
    assert not hasattr(schemas, 'EntityJobSchema')

def test_routes_annotation():
    from store.m_insight import routes
    from store.db_service import schemas as db_schemas
    from typing import get_type_hints
    
    # Verify routes uses db_service schemas directly
    # routes.EntityJobSchema is imported from db_service
    assert routes.EntityJobSchema is db_schemas.EntityJobSchema
    
    # Check resolved annotation
    hints = get_type_hints(routes.get_entity_jobs)
    assert hints['return'] == list[db_schemas.EntityJobSchema]

def test_compat():
    # Verify EntityJobResponse is GONE
    from store.m_insight import schemas
    assert not hasattr(schemas, 'EntityJobResponse')
    # Verify other deleted schemas
    assert not hasattr(schemas, 'FaceResponse')
    assert not hasattr(schemas, 'KnownPersonResponse')
    assert not hasattr(schemas, 'FaceMatchResult')
    assert not hasattr(schemas, 'EntityVersionData')
    
    # Verify new imports
    assert hasattr(schemas, 'FaceSchema')
    assert hasattr(schemas, 'KnownPersonSchema')
