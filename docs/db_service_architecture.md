# DB Service Architecture

This document provides a visual reference for the `db_service` module, including database tables, Pydantic schemas, and available service methods.

## Database Tables (ER Diagram)

The following diagram represents the SQLAlchemy models defined in `store.db_service.models`.

```mermaid
erDiagram
    Entity {
        int id PK
        bool is_collection
        string label
        string description
        int parent_id FK
        int added_date
        int updated_date
        int create_date
        string added_by
        string updated_by
        int file_size
        int height
        int width
        float duration
        string mime_type
        string type
        string extension
        string md5
        string file_path
        bool is_deleted
        json intelligence_data
    }

    Face {
        int id PK
        int entity_id FK
        int known_person_id FK
        text bbox
        float confidence
        text landmarks
        string file_path
        int created_at
    }

    KnownPerson {
        int id PK
        string name
        int created_at
        int updated_at
    }

    ServiceConfig {
        string key PK
        string value
        int updated_at
        string updated_by
    }

    EntitySyncState {
        int id PK
        int last_version
    }

    Entity ||--o{ Entity : "children (parent_id)"
    Entity ||--o{ Face : "faces"
    KnownPerson ||--o{ Face : "faces"
```

## Data Schemas (Pydantic Models)

The following diagram represents the Pydantic schemas defined in `store.db_service.schemas`. These schemas are used for data exchange and API responses.

```mermaid
classDiagram
    class EntitySchema {
        +int id
        +bool is_collection
        +str label
        +str description
        +int parent_id
        +int added_date
        +int updated_date
        +int create_date
        +str added_by
        +str updated_by
        +int file_size
        +int height
        +int width
        +float duration
        +str mime_type
        +str type
        +str extension
        +str md5
        +str file_path
        +bool is_deleted
        +bool is_indirectly_deleted
        +EntityIntelligenceData intelligence_data
    }

    class EntityIntelligenceData {
        +str overall_status
        +str last_processed_md5
        +int last_processed_version
        +int face_count
        +str active_processing_md5
        +List[JobInfo] active_jobs
        +InferenceStatus inference_status
        +int last_updated
        +str error_message
    }

    class JobInfo {
        +str job_id
        +str task_type
        +int started_at
    }

    class InferenceStatus {
        +str face_detection
        +str clip_embedding
        +str dino_embedding
        +List[str] face_embeddings
    }

    class EntityVersionSchema {
        +int id
        +bool is_collection
        +str label
        +int parent_id
        +str md5
        +bool is_deleted
        +int transaction_id
        +int operation_type
    }

    class FaceSchema {
        +int id
        +int entity_id
        +int known_person_id
        +BBox bbox
        +float confidence
        +FaceLandmarks landmarks
        +str file_path
        +int created_at
    }

    class KnownPersonSchema {
        +int id
        +str name
        +int created_at
        +int updated_at
        +int face_count
    }

    EntitySchema *-- EntityIntelligenceData
    EntityIntelligenceData *-- JobInfo
    EntityIntelligenceData *-- InferenceStatus
```

## Service Layer (API)

The data access layer consists of specialized service classes inhering from `BaseDBService`. These services handle database sessions, retries, and transaction management.

```mermaid
classDiagram
    class BaseDBService~SchemaT~ {
        +get(id: int) -> SchemaT | None
        +get_all(page, page_size) -> List[SchemaT]
        +create(data: SchemaT, ignore_exception) -> SchemaT | None
        +update(id: int, data: SchemaT, ignore_exception) -> SchemaT | None
        +delete(id: int) -> bool
        +query(**kwargs) -> List[SchemaT]
        +count(**kwargs) -> int
    }

    class EntityDBService {
        +get_or_raise(id: int) -> EntitySchema
        +update_intelligence_data(id: int, data) -> EntitySchema | None
        +get_children(parent_id: int) -> List[EntitySchema]
        +delete_all()
    }

    class EntityVersionDBService {
        +get_all_for_entity(entity_id) -> List[EntityVersionSchema]
        +get_by_transaction_id(entity_id, transaction_id) -> EntityVersionSchema | None
        +get_versions_in_range(start_tid, end_tid) -> Dict[int, EntityVersionSchema]
        +query(**kwargs) -> List[EntityVersionSchema]
    }

    class ConfigDBService {
        +get_config_metadata(key) -> dict | None
        +set_read_auth_enabled(enabled, user_id)
        +get_read_auth_enabled() -> bool
    }

    class FaceDBService {
        +get_all_for_entity(entity_id) -> List[FaceSchema]
        +delete_all_for_entity(entity_id)
        +assign_person(face_id, person_id) -> FaceSchema | None
    }

    class KnownPersonDBService {
        +get_or_create(name) -> KnownPersonSchema
        +merge_persons(source_id, target_id)
    }

    BaseDBService <|-- EntityDBService
    BaseDBService <|-- ConfigDBService
    BaseDBService <|-- FaceDBService
    BaseDBService <|-- KnownPersonDBService
```
