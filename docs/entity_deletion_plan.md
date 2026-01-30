# Implementation Plan: Modular Entity Deletion with Full Cleanup

## Goal Description
Refactor the entity deletion logic to be modular, robust, and ensure complete cleanup of all associated data (files, vector embeddings, MQTT messages, and database records).

## User Review Required
> [!NOTE]
> **Phased Approach**:
> - **Phase 1 (Complete)**: Removed existing endpoints and the toxic `delete_all_entities` code.
> - **Phase 2 (Current)**: Implement new services and orchestration.

> [!CAUTION]
> **Why IDs were Reused (Solved)**:
> I have confirmed why IDs were being reused. The previous `delete_collection` endpoint called `service.delete_all_entities()`.
> That method contained this exact line:
> ```python
> _ = self.db.execute(text("DELETE FROM sqlite_sequence"))
> ```
> This command **explicitly** resets the auto-increment counter. By removing this method in Phase 1, we have **already fixed the root cause**. Normal deletion will now respect the `sqlite_sequence` and *never* reuse IDs.

## Proposed Changes

## Requirements & Design

### Coding Standards
> [!IMPORTANT]
> **Append-Only Policy**: All new methods, classes, and logic should be added to the **END** of existing files/classes to minimize merge conflicts and maintain readability.

### Deletion Logic Specification
| ID         | Requirement Statement                                                                                                                                                | Test Case                               |
| ID         | Requirement Statement                                                                                                                                                                                                          | Test Case                                    |
| :--------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------- |
| **DEL-01** | **Entity Removal**: Deleting an entity by ID `DELETE /entities/{id}` must remove the entity record from the database.                                                                                                          | `test_delete_entity_removes_db_record`       |
| **DEL-02** | **File Cleanup**: Deleting an entity must remove its associated file from the filesystem.                                                                                                                                      | `test_delete_entity_removes_file`            |
| **DEL-03** | **Vector Cleanup**: Deleting an entity must remove its CLIP/DINO embeddings. **Test must confirm embeddings exist first.**                                                                                                     | `test_delete_entity_removes_vectors`         |
| **DEL-04** | **Face Cleanup**: Deleting an entity must remove all associated Face records/vectors.                                                                                                                                          | `test_delete_entity_removes_faces`           |
| **DEL-05** | **MQTT Cleanup**: Deleting an entity must clear any retained MQTT messages.                                                                                                                                                    | `test_delete_entity_clears_mqtt`             |
| **DEL-06** | **Collection Deletion**: Deleting a Collection **MUST** recursively delete all children. **CRITICAL**: If a child is not already soft-deleted, it MUST be soft-deleted first (to create version history) before hard deletion. | `test_recursive_deletion_soft_deletes_first` |
| **DEL-07** | **Single Target Only**: NO "Delete All" endpoint.                                                                                                                                                                              | `test_delete_all_not_exposed`                |
| **DEL-08** | **Face Deletion Endpoint**: `DELETE /faces/{id}` must remove face from DB, Storage, Vector Store, and **decrement `face_count`** in Entity Intelligence.                                                                       | `test_delete_face_updates_counts`            |
| **DEL-09** | **Hard Delete Pre-condition**: An entity must be **Soft Deleted** (`is_deleted=True` OR `is_indirectly_deleted=True`) before it can be permanently deleted.                                                                    | `test_hard_delete_requires_soft_delete`      |
| **DEL-10** | **Clear Orphans**: `POST /system/clear-orphans` scans for and removes all resources (Files, Faces, Vectors, MQTT) that do not have a corresponding Entity in the DB.                                                           | `test_clear_orphans`                         |

### New Component: Audit Service
**Goal**: Provide an on-demand report of data integrity issues.
- **Endpoint**: `GET /system/audit`
- **Output**: JSON Report
- **Checks**:
    1.  **Orphaned Files**: Scan `media_storage_dir`. Report files that do not have a corresponding `Entity` record.
    2.  **Orphaned MQTT**: Scan retained topics (via helper or internal tracking). Report topics for IDs that do not exist.
    3.  **Orphaned Faces**: Report Face records in DB without valid Entity IDs.
    4.  **Vector Integrity**: Check Qdrant collections (CLIP, DINO, Faces) for IDs that do not exist in the DB (Orphans).
- **Methods**:
    - `generate_report() -> AuditReport`: Runs all checks.
    - `clear_orphans(report: AuditReport) -> CleanupReport`: Deletes the orphaned resources identified.

### Proposed Changes

#### [NEW] [FaceService](file:///Users/anandasarangaram/Work/cl_server/services/store/src/store/store/face_service.py)
**Location**: `services/store/src/store/store/face_service.py`
- **Purpose**: Encapsulate Face lifecycle (DB + Vector + File deletion).
- **Methods**:
    - `delete_face(face_id: int) -> bool`:
        - Get face details (path, ID).
        - **Vector**: Delete from Qdrant.
        - **File**: Delete from Filesystem keys.
        - **DB**: Delete Face record.
        - **Update**: Decrement `face_count` on parent Entity.
    - `delete_faces_for_entity(entity_id: int)`: Deletes DB records, Qdrant points, and crop images.

#### [NEW] [AuditService](file:///Users/anandasarangaram/Work/cl_server/services/store/src/store/store/audit_service.py)
**Location**: `services/store/src/store/store/audit_service.py`
- **Purpose**: readonly data integrity checks.
- **Methods**:
    - `generate_report() -> AuditReport`: Runs all checks and returns a Pydantic model.

#### [MODIFY] [EntityService](file:///Users/anandasarangaram/Work/cl_server/services/store/src/store/store/service.py)
- **Update**: `delete_entity(entity_id: int)`
    - **Step 1**: Check IF Collection -> Get Children.
        - For each child:
            - **If child not soft-deleted**: Perform Soft Delete (PATCH `is_deleted=True`) to ensure version history.
            - Call `delete_entity(child.id)` (Recursive Hard Delete).
    - **Step 2**: **Verify Self is Soft Deleted**. If not, raise Error (DEL-09).
    - **Step 3**: `face_service.delete_faces_for_entity(id)`
    - **Step 4**: `vector_store.delete(id)` (CLIP/DINO)
    - **Step 5**: `storage_service.delete(path)`
    - **Step 6**: `broadcaster.clear_retained(id)`
    - **Step 7**: `db.delete(id)`

#### [MODIFY] [routes.py](file:///Users/anandasarangaram/Work/cl_server/services/store/src/store/store/routes.py)
- **Add**: `DELETE /entities/{entity_id}`
- **Add**: `DELETE /faces/{face_id}`
- **Add**: `GET /system/audit`
- **Add**: `POST /system/clear-orphans`
- **Explicitly Exclude**: Any bulk delete route.
- **Location**: Add new routes at the **END** of the file/router.

## Verification Plan
## Verification Plan

### Automated Integration Test
- **File**: `tests/test_store/test_integration/test_store_delete.py`
- **Coverage**: This file will implement the test cases defined in the "Deletion Logic Specification" table above (DEL-01 to DEL-07).

### Audit Test
- **File**: `tests/test_store/test_integration/test_audit.py`
- **Scenario**:
    1.  Create Valid Entity (should NOT appear in audit).
    2.  Create "Ghost" file in storage (should appear in audit).
    3.  Simulate Orphaned MQTT topic (if testable).
    4.  Call `GET /system/audit` -> Verify report correctness.
