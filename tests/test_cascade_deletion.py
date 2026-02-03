"""Tests for recursive cascade deletion of collections with children."""

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from store.db_service.db_internals import Entity


def test_soft_delete_collection_with_children(
    client: TestClient,
    sample_image: Path,
    test_db_session: Session,
) -> None:
    """Test that soft-deleting a collection does not soft-delete its children."""
    # Create a collection
    response = client.post(
        "/entities/",
        data={"label": "Test Collection", "is_collection": "true"},
    )
    assert response.status_code == 201
    collection_id = response.json()["id"]

    # Create a child image in the collection
    with sample_image.open("rb") as f:
        response = client.post(
            "/entities/",
            files={"image": ("test.jpg", f, "image/jpeg")},
            data={
                "label": "Child Image",
                "is_collection": "false",
                "parent_id": str(collection_id),
            },
        )
    assert response.status_code == 201
    child_id = response.json()["id"]

    # Soft-delete the collection
    collection = test_db_session.query(Entity).filter(Entity.id == collection_id).first()
    assert collection is not None
    collection.is_deleted = True
    test_db_session.commit()

    # Verify collection is soft-deleted
    collection = test_db_session.query(Entity).filter(Entity.id == collection_id).first()
    assert collection.is_deleted is True

    # Verify child is NOT soft-deleted
    child = test_db_session.query(Entity).filter(Entity.id == child_id).first()
    assert child.is_deleted is False


def test_hard_delete_collection_cascades_to_children(
    client: TestClient,
    sample_image: Path,
    test_db_session: Session,
    clean_data_dir: Path,
) -> None:
    """Test that hard-deleting a soft-deleted collection cascades to children."""
    # Create a collection
    response = client.post(
        "/entities/",
        data={"label": "Test Collection", "is_collection": "true"},
    )
    assert response.status_code == 201
    collection_id = response.json()["id"]

    # Create a child image in the collection
    with sample_image.open("rb") as f:
        response = client.post(
            "/entities/",
            files={"image": ("test.jpg", f, "image/jpeg")},
            data={
                "label": "Child Image",
                "is_collection": "false",
                "parent_id": str(collection_id),
            },
        )
    assert response.status_code == 201
    child_id = response.json()["id"]

    # Soft-delete collection first
    from store.store.config import StoreConfig
    from store.store.service import EntityService

    config = StoreConfig(
        cl_server_dir=clean_data_dir,
        media_storage_dir=clean_data_dir / "media",
        public_key_path=clean_data_dir / "keys" / "public_key.pem",
        no_auth=True,
        port=8001,
        mqtt_url="mqtt://mock-broker:1883",
    )
    service = EntityService(test_db_session, config)
    service.patch_entity(collection_id, {"is_deleted": True})

    # Hard delete the collection (route does soft-delete + hard-delete)
    response = client.delete(f"/entities/{collection_id}")
    assert response.status_code == 204

    # Verify both collection and child are hard-deleted
    collection = test_db_session.query(Entity).filter(Entity.id == collection_id).first()
    assert collection is None

    child = test_db_session.query(Entity).filter(Entity.id == child_id).first()
    assert child is None


def test_hard_delete_nested_collections_cascades_recursively(
    client: TestClient,
    sample_image: Path,
    test_db_session: Session,
    clean_data_dir: Path,
) -> None:
    """Test that hard-deleting a collection recursively cascades through nested children."""
    # Create parent collection
    response = client.post(
        "/entities/",
        data={"label": "Parent Collection", "is_collection": "true"},
    )
    assert response.status_code == 201
    parent_id = response.json()["id"]

    # Create child collection
    response = client.post(
        "/entities/",
        data={
            "label": "Child Collection",
            "is_collection": "true",
            "parent_id": str(parent_id),
        },
    )
    assert response.status_code == 201
    child_collection_id = response.json()["id"]

    # Create grandchild image
    with sample_image.open("rb") as f:
        response = client.post(
            "/entities/",
            files={"image": ("test.jpg", f, "image/jpeg")},
            data={
                "label": "Grandchild Image",
                "is_collection": "false",
                "parent_id": str(child_collection_id),
            },
        )
    assert response.status_code == 201
    grandchild_id = response.json()["id"]

    # Soft-delete parent collection first
    from store.store.config import StoreConfig
    from store.store.service import EntityService

    config = StoreConfig(
        cl_server_dir=clean_data_dir,
        media_storage_dir=clean_data_dir / "media",
        public_key_path=clean_data_dir / "keys" / "public_key.pem",
        no_auth=True,
        port=8001,
        mqtt_url="mqtt://mock-broker:1883",
    )
    service = EntityService(test_db_session, config)
    service.patch_entity(parent_id, {"is_deleted": True})

    # Hard delete the parent collection
    response = client.delete(f"/entities/{parent_id}")
    assert response.status_code == 204

    # Verify all are hard-deleted
    parent = test_db_session.query(Entity).filter(Entity.id == parent_id).first()
    assert parent is None

    child_collection = test_db_session.query(Entity).filter(Entity.id == child_collection_id).first()
    assert child_collection is None

    grandchild = test_db_session.query(Entity).filter(Entity.id == grandchild_id).first()
    assert grandchild is None
