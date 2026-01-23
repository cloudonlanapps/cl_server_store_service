# Architecture Documentation - services/store

This document provides a detailed overview of the class structure, service relationships, and database schema for the `services/store` module.

## Class & Database Diagram

The following Mermaid diagram visualizes the interaction between the service layer, the asynchronous processing layer (m_insight), and the persistence layer (SQLAlchemy models).

```mermaid
classDiagram
    direction TB

    %% Service Layer
    namespace Services {
        class EntityService {
            -Session db
            -StoreConfig config
            +create_entity()
            +update_entity()
            +get_entities()
            +patch_entity()
        }
        class StorageService {
            -Path base_dir
            +save_file()
            +delete_file()
            +get_absolute_path()
        }
        class IntelligenceRetrieveService {
            -Session db
            +search_similar_images()
            +search_similar_faces_by_id()
        }
    }

    %% Async Processing Layer (m_insight)
    namespace ML_Processing {
        class MediaInsight {
            -JobSubmissionService jobs
            -MInsightBroadcaster broadcaster
            +run_once()
            +process()
            -_trigger_async_jobs()
        }
        class JobSubmissionService {
            -ComputeClient compute
            +submit_face_detection()
            +submit_clip_embedding()
            +submit_dino_embedding()
        }
        class JobCallbackHandler {
            -QdrantVectorStore clip_store
            -QdrantVectorStore face_store
            +handle_face_detection_complete()
            +handle_clip_embedding_complete()
            +handle_face_embedding_complete()
        }
    }

    %% Database Models
    namespace Models {
        class Entity {
            <<Table: entities>>
            +int id
            +str md5
            +str path
            +bool is_collection
        }
        class ImageIntelligence {
            <<Table: image_intelligence>>
            +int entity_id
            +str status
            +int version
        }
        class Face {
            <<Table: faces>>
            +int id
            +int entity_id
            +int person_id
            +JSON bbox
        }
        class EntityJob {
            <<Table: entity_jobs>>
            +str job_id
            +str status
            +int entity_id
        }
        class KnownPerson {
            <<Table: known_persons>>
            +int id
            +str name
        }
    }

    %% Vector Stores
    namespace VectorDB {
        class QdrantVectorStore {
            +add_vector()
            +search()
        }
    }

    %% Relationships - Services to Models
    EntityService ..> Entity : CRUD
    IntelligenceRetrieveService ..> Face : queries
    IntelligenceRetrieveService ..> KnownPerson : queries
    
    %% Relationships - Processing to Services/Models
    MediaInsight --> JobSubmissionService : uses
    JobSubmissionService ..> EntityJob : tracks
    
    %% Callback flow
    JobCallbackHandler ..> Face : updates/creates
    JobCallbackHandler ..> ImageIntelligence : updates status
    JobCallbackHandler ..> QdrantVectorStore : upserts embeddings
    
    %% Data Ownership
    Entity "1" *-- "0..1" ImageIntelligence : has
    Entity "1" *-- "0..n" EntityJob : tracks
    Entity "1" *-- "0..n" Face : contains
    KnownPerson "1" *-- "0..n" Face : identified_by
    
    %% External dependencies
    JobSubmissionService ..> StorageService : path resolution
    JobCallbackHandler ..> StorageService : saves face crops
```

## Summary of Components

### Core Services
- **EntityService**: Handles the main logic for file uploads, metadata management, and collection structure. Interacts directly with the `entities` table.
- **StorageService**: Responsible for filesystem abstraction (saving/deleting files based on MD5 paths).

### Media Insight (ML)
- **MediaInsight**: A background reconciler that compares entity versions and enqueues tasks for missing intelligence metadata.
- **JobSubmissionService**: Wraps the `ComputeClient` to submit specific tasks (CLIP, DINO, Face) to the ML worker cluster.
- **JobCallbackHandler**: The logic that runs when a job finishes. It downloads results, updates the database models, and pushes vectors to Qdrant.

### Database Schema
- **entities**: The central table for all files and folders.
- **image_intelligence**: Parallel table tracking the ML processing status and version for each image.
- **faces**: Individual faces detected within an image, linked to a `KnownPerson` if matched using embeddings.
- **known_persons**: Unique identities verified across the entire library.
