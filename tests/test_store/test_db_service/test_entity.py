from store.db_service import EntitySchema

def test_entity_crud(db_service):
    # Create
    entity_data = EntitySchema(
        id=1,
        label="Test Entity",
        file_path="/tmp/test.jpg",
        is_collection=False
    )
    created = db_service.entity.create(entity_data)
    assert created is not None
    assert created.id == 1
    assert created.label == "Test Entity"

    # Get
    retrieved = db_service.entity.get(1)
    assert retrieved is not None
    assert retrieved.id == 1
    assert retrieved.label == "Test Entity"

    # Update
    update_data = EntitySchema(
        id=1,
        label="Updated Entity"
    )
    updated = db_service.entity.update(1, update_data)
    assert updated is not None
    assert updated.label == "Updated Entity"
    
    # Get again
    retrieved = db_service.entity.get(1)
    assert retrieved.label == "Updated Entity"

    # Delete
    deleted = db_service.entity.delete(1)
    assert deleted is True
    
    # Get again -> None
    retrieved = db_service.entity.get(1)
    assert retrieved is None

def test_pagination(db_service):
    # Create 25 entities
    for i in range(25):
        db_service.entity.create(EntitySchema(id=i+100, label=f"Entity {i}"))

    # Page 1
    items, total = db_service.entity.get_all(page=1, page_size=10)
    assert len(items) == 10
    assert total == 25
    assert items[0].label == "Entity 0"

    # Page 3
    items, total = db_service.entity.get_all(page=3, page_size=10)
    assert len(items) == 5
    assert total == 25
    assert items[0].label == "Entity 20"

def test_query(db_service):
    db_service.entity.create(EntitySchema(id=200, label="Alpha", file_size=100))
    db_service.entity.create(EntitySchema(id=201, label="Beta", file_size=200))
    db_service.entity.create(EntitySchema(id=202, label="Gamma", file_size=300))

    # Exact match
    results = db_service.entity.query(label="Beta")
    assert len(results) == 1
    assert results[0].id == 201

    # Greater than
    results = db_service.entity.query(file_size__gt=150)
    assert len(results) == 2
    assert {r.id for r in results} == {201, 202}

    # Ordering
    results = db_service.entity.query(order_by="file_size", ascending=False)
    assert results[0].label == "Gamma"
    assert results[2].label == "Alpha"
