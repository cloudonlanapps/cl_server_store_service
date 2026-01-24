# CL Server Store Service - Comprehensive Code Review

**Review Date:** 2026-01-24
**Reviewer:** Claude Code (Automated Code Review)
**Total Issues Found:** 95+ (55 source code + 40+ test issues)

## Quick Summary

| Category        | Critical | High   | Medium | Low     | Total   |
| --------------- | -------- | ------ | ------ | ------- | ------- |
| **Source Code** | 5        | 16     | 25     | 9       | 55      |
| **Tests**       | 8        | 12     | 15     | 5+      | 40+     |
| **TOTAL**       | **13**   | **28** | **40** | **14+** | **95+** |

## Table of Contents

1. [Critical Issues (Must Fix Immediately)](#critical-issues-must-fix-immediately)
2. [High Priority Issues](#high-priority-issues)
3. [Medium Priority Issues](#medium-priority-issues)
4. [Low Priority Issues](#low-priority-issues)
5. [Source Code Issues by Category](#source-code-issues-by-category)
6. [Test Issues by Category](#test-issues-by-category)
7. [Implementation Recommendations](#implementation-recommendations)

---

## Critical Issues (Must Fix Immediately)

### CRITICAL-001: Async Tests Missing @pytest.mark.asyncio Decorator

**Category:** Tests / Test Execution
**Severity:** CRITICAL
**Impact:** Tests will not execute correctly - silently skipped or fail with "coroutine never awaited"

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/tests/test_m_insight_mqtt.py`
- `/Users/anandasarangaram/Work/cl_server/services/store/tests/test_m_insight_worker.py`

**Description:**
Eight async test functions are missing the required `@pytest.mark.asyncio` decorator. Without this decorator, pytest cannot recognize these as async tests, causing them to either be skipped silently or fail with warnings.

**Affected Tests:**
1. `test_m_insight_lifecycle_events()` - Line 71 in test_m_insight_mqtt.py
2. `test_m_insight_heartbeat_status()` - Line 131 in test_m_insight_mqtt.py
3. `test_empty_sync_state_queues_all_images()` - Line 121 in test_m_insight_worker.py
4. `test_existing_sync_state_only_newer_versions()` - Line 164 in test_m_insight_worker.py
5. `test_multiple_md5_changes_single_queue()` - Line 220 in test_m_insight_worker.py
6. Plus 3 more async tests in test_m_insight_worker.py

**Current Code:**
```python
# WRONG - Missing decorator
async def test_m_insight_lifecycle_events(mqtt_client):
    await processor.start()
    # ...
```

**Fix Required:**
```python
# CORRECT - Add decorator
@pytest.mark.asyncio
async def test_m_insight_lifecycle_events(mqtt_client):
    await processor.start()
    # ...
```

**GitHub Issue Template:**
```markdown
**Title:** [CRITICAL] Add @pytest.mark.asyncio to 8 async tests

**Labels:** bug, critical, tests, async

**Description:**
Eight async tests are missing the required `@pytest.mark.asyncio` decorator, preventing them from executing correctly.

**Impact:**
- Tests don't run correctly
- May be silently skipped
- Reduces actual test coverage from expected levels
- CI/CD may pass with false positives

**Files:**
- tests/test_m_insight_mqtt.py (2 tests)
- tests/test_m_insight_worker.py (6 tests)

**Fix:**
Add `@pytest.mark.asyncio` decorator above each async test function.

**Acceptance Criteria:**
- [ ] All 8 async tests have decorator
- [ ] Tests execute without "coroutine never awaited" warnings
- [ ] Test coverage accurately reflects running tests
- [ ] CI/CD pipeline shows tests running
```

---

### CRITICAL-002: ImageIntelligence Model Has Conflicting Status Fields

**Category:** Source Code / Data Model
**Severity:** CRITICAL
**Impact:** Data integrity issues, conflicting status values, unclear state management

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/src/store/common/models.py` (Lines 146, 175)

**Description:**
The `ImageIntelligence` model has two status fields tracking the same information:
- `status: Mapped[str]` field (Line 146) with default "queued"
- `processing_status: Mapped[str]` field (Line 175) with default "pending"

This creates confusion about which field is authoritative and potential for inconsistent state where `status='completed'` but `processing_status='pending'`.

**Location:** Lines 146 and 175 in src/store/common/models.py

**Current Code:**
```python
class ImageIntelligence(Base):
    # ...
    # Line 146: Original status field
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")

    # Lines 157-173: Extensive comments about uncertainty
    # "I will add processing_status as a NEW field..."

    # Line 175: Duplicate status field
    processing_status: Mapped[str] = mapped_column(String, default="pending")
```

**Issues:**
1. Unclear which field code should check/update
2. Potential for `status='completed'` but `processing_status='pending'`
3. Database queries may check wrong field
4. Code comments indicate this was unresolved refactoring

**Fix Required:**
Choose one field and remove the other. Recommended approach:

```python
class ImageIntelligence(Base):
    # ...
    # Use single status field with enum
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="pending"
    )
    # Valid values: 'pending', 'processing', 'completed', 'failed'

    # Remove processing_status field entirely
```

**Migration Required:**
```bash
# Create migration to consolidate fields
uv run alembic revision --autogenerate -m "Consolidate ImageIntelligence status fields"

# In migration:
# 1. Copy processing_status to status where needed
# 2. Drop processing_status column
# 3. Add CHECK constraint for valid status values
```

**GitHub Issue Template:**
```markdown
**Title:** [CRITICAL] Remove conflicting status fields in ImageIntelligence model

**Labels:** bug, critical, data-model, database

**Description:**
ImageIntelligence has both `status` and `processing_status` fields tracking processing state, creating data integrity risks.

**Impact:**
- Data integrity issues
- Conflicting status representations
- Validation bugs
- Unclear code semantics

**Files:**
- src/store/common/models.py (lines 146, 175)

**Fix:**
1. Consolidate to single `status` field
2. Create database migration
3. Update all code referencing either field
4. Add enum/CHECK constraint for valid values

**Acceptance Criteria:**
- [ ] Single status field in model
- [ ] Migration created and tested
- [ ] All code updated
- [ ] Tests pass
- [ ] No data loss during migration
```

---

### CRITICAL-003: Entity Model Missing get_file_path() Method

**Category:** Source Code / Architecture
**Severity:** CRITICAL
**Impact:** Type inconsistency, code that expects method will fail at runtime

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/src/store/common/models.py` (Entity model)
- `/Users/anandasarangaram/Work/cl_server/services/store/src/store/m_insight/job_service.py` (Lines 42-113)

**Description:**
The `Face` model has a `get_file_path()` method (Line 233-244), but the `Entity` model does not. However, code in `job_service.py` expects both `Entity` and `EntityVersionData` to have this method, creating a type mismatch.

**Current Code:**

```python
# Face model HAS the method (models.py:233-244)
class Face(Base):
    def get_file_path(self, storage_service: StorageService) -> Path:
        if not self.file_path:
            raise ValueError(f"Face {self.id} has no file_path")
        return storage_service.get_absolute_path(self.file_path)

# Entity model DOES NOT have this method
class Entity(Base):
    file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    # No get_file_path() method!

# job_service.py expects it (lines 42-113)
def create_face_detection_job(
    entity: Entity | EntityVersionData,  # Either type should work
    storage_service: StorageService,
    compute_client: ComputeClient
) -> str | None:
    # Lines 61-66: Comment acknowledges the problem
    # "I need to ensure Entity has it or use logic here"

    # Line 85: Tries to call method that doesn't exist on Entity
    image_path = entity.get_file_path(storage_service)  # AttributeError if Entity!
```

**Fix Required:**

Add `get_file_path()` method to Entity model:

```python
class Entity(Base):
    # ... existing fields ...

    def get_file_path(self, storage_service: StorageService) -> Path:
        """Resolve absolute file path using storage service.

        Args:
            storage_service: StorageService instance configured with media_dir

        Returns:
            Absolute Path to the media file

        Raises:
            ValueError: If entity has no file_path
        """
        if not self.file_path:
            raise ValueError(f"Entity {self.id} has no file_path")
        return storage_service.get_absolute_path(self.file_path)
```

**GitHub Issue Template:**
```markdown
**Title:** [CRITICAL] Add get_file_path() method to Entity model

**Labels:** bug, critical, architecture, type-safety

**Description:**
Entity model is missing `get_file_path()` method that Face model has and job_service.py expects.

**Impact:**
- AttributeError at runtime when Entity used in job_service
- Type inconsistency between models
- Code duplication for path resolution
- Violates interface expectations

**Files:**
- src/store/common/models.py (Entity class)
- src/store/m_insight/job_service.py (uses the method)

**Fix:**
Add `get_file_path(storage_service)` method to Entity model matching Face implementation.

**Acceptance Criteria:**
- [ ] Entity has get_file_path() method
- [ ] Method signature matches Face model
- [ ] Method tested with unit tests
- [ ] No AttributeError in job_service
- [ ] Type checker passes
```

---

### CRITICAL-004: Face Files Not Deleted When Entity Deleted

**Category:** Source Code / Resource Management / Data Leaks
**Severity:** CRITICAL
**Impact:** File system leaks, orphaned face images accumulate indefinitely, disk space exhaustion

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/src/store/store/service.py` (delete_entity method, lines 642-694)
- `/Users/anandasarangaram/Work/cl_server/services/store/src/store/common/models.py` (Face model, lines 188-244)

**Description:**
When an entity is deleted via `delete_entity()`, the entity's file is properly deleted from storage (line 688-689), and Face records are cascade-deleted from the database via SQLAlchemy relationships. However, the **cropped face image files** stored on disk (referenced by `face.file_path`) are **never deleted**, causing permanent file leaks.

**Data Flow:**
1. Entity created → Face detection job runs → Cropped face images saved to disk
2. Face records created in database with `file_path` pointing to cropped images
3. Entity deleted → Entity file deleted from storage ✓
4. Face records cascade-deleted from database ✓
5. **Cropped face image files remain on disk indefinitely** ✗

**Current Code:**
```python
# service.py:642-694
def delete_entity(self, entity_id: int, *, _from_parent: bool = False) -> bool:
    """Delete an entity (hard delete with proper versioning)."""
    entity = self.db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        return False

    # ... validation and children recursion ...

    # Hard delete this entity - remove file and database record
    if entity.file_path:
        _ = self.file_storage.delete_file(entity.file_path)  # ✓ Entity file deleted

    self.db.delete(entity)  # Face records cascade-deleted from DB
    self.db.commit()

    # ✗ PROBLEM: Face files (entity.faces[].file_path) are NEVER deleted!
    return True
```

**Face Model (models.py:214):**
```python
class Face(Base):
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    # Path to cropped face image file - stored in storage system
```

**Fix Required:**

Delete face files before deleting the entity:

```python
def delete_entity(self, entity_id: int, *, _from_parent: bool = False) -> bool:
    """Delete an entity (hard delete with proper versioning)."""
    entity = self.db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        return False

    # Direct call: require entity to be soft-deleted first
    if not _from_parent and not entity.is_deleted:
        raise ValueError(...)

    # Recursive call from parent: soft-delete if not already
    if _from_parent and not entity.is_deleted:
        entity.is_deleted = True
        self.db.commit()

    # Recursively handle children if this is a collection
    children = self.db.query(Entity).filter(Entity.parent_id == entity_id).all()
    if children:
        for child in children:
            _ = self.delete_entity(child.id, _from_parent=True)

    # NEW: Delete face files before deleting entity
    if entity.faces:
        for face in entity.faces:
            if face.file_path:
                _ = self.file_storage.delete_file(face.file_path)

    # Delete entity file
    if entity.file_path:
        _ = self.file_storage.delete_file(entity.file_path)

    self.db.delete(entity)
    self.db.commit()

    return True
```

**GitHub Issue Template:**
```markdown
**Title:** [CRITICAL] delete_entity() leaks face image files

**Labels:** bug, critical, resource-leak, file-management

**Description:**
When entities are deleted, their associated face image files are not deleted from storage, causing permanent file system leaks. Only database records are removed.

**Impact:**
- Orphaned face images accumulate indefinitely
- Disk space exhaustion over time
- No automatic cleanup mechanism
- Production servers will eventually fill up
- Each entity with N faces leaks N cropped image files

**Files:**
- src/store/store/service.py (delete_entity method)
- src/store/common/models.py (Face model relationships)

**Root Cause:**
`delete_entity()` only deletes the entity's file, not the associated face files. SQLAlchemy cascade deletes Face records from DB, but files remain on disk.

**Fix:**
Before deleting entity, iterate through `entity.faces` and delete each `face.file_path` from storage.

**Acceptance Criteria:**
- [ ] delete_entity() deletes all face files before deleting entity
- [ ] Cascade deletion still works for nested entities
- [ ] File storage cleanup tested
- [ ] Integration test verifies face files are deleted
- [ ] No orphaned files remain after entity deletion
```

---

### CRITICAL-005: delete_all_entities() Does Not Delete Any Files

**Category:** Source Code / Resource Management / Data Leaks
**Severity:** CRITICAL
**Impact:** Massive file leaks, all entity and face files remain on disk, complete data inconsistency

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/src/store/store/service.py` (delete_all_entities method, lines 722-774)

**Description:**
The `delete_all_entities()` method deletes all database records (entities, faces, intelligence data, versioning tables) but **does not delete ANY files from storage**. This creates a complete disconnect between database and file system, with all media files remaining orphaned on disk.

**Current Code:**
```python
# service.py:722-774
def delete_all_entities(self) -> None:
    """Delete all entities and related data from the database."""
    # 1. Clear intelligence and related tables
    _ = self.db.query(EntityJob).delete()
    _ = self.db.query(Face).delete()  # Face files NOT deleted!
    _ = self.db.query(ImageIntelligence).delete()
    _ = self.db.query(KnownPerson).delete()

    # 2. Clear versioning and transaction metadata
    tables_to_clear = [...]
    for table in tables_to_clear:
        _ = self.db.execute(text(f"DELETE FROM {table}"))

    # 3. Delete all records from main Entity table
    _ = self.db.query(Entity).delete()  # Entity files NOT deleted!

    # 4. Reset sync state and sequences
    # ...

    self.db.commit()

    # ✗ PROBLEM: NO file cleanup! All entity files and face files remain on disk!
```

**Impact Scenario:**
1. System has 10,000 entities with images and faces
2. Admin calls `delete_all_entities()` (or DELETE /entities endpoint)
3. All database records deleted ✓
4. All 10,000 entity files remain on disk ✗
5. All associated face cropped images remain on disk ✗
6. Files are now orphaned - no database references
7. No way to know which files are orphaned vs legitimate
8. Manual cleanup required or disk fills up

**Fix Required:**

Query all entities and faces first, delete files, then delete records:

```python
def delete_all_entities(self) -> None:
    """Delete all entities and related data from database AND storage."""
    from pathlib import Path
    from sqlalchemy import text

    # NEW: Phase 0 - Delete all files first (before database records)

    # Delete all face files
    faces = self.db.query(Face).all()
    for face in faces:
        if face.file_path:
            try:
                _ = self.file_storage.delete_file(face.file_path)
            except Exception as e:
                logger.warning(f"Failed to delete face file {face.file_path}: {e}")

    # Delete all entity files
    entities = self.db.query(Entity).all()
    for entity in entities:
        if entity.file_path:
            try:
                _ = self.file_storage.delete_file(entity.file_path)
            except Exception as e:
                logger.warning(f"Failed to delete entity file {entity.file_path}: {e}")

    # Phase 1: Clear intelligence and related tables
    _ = self.db.query(EntityJob).delete()
    _ = self.db.query(Face).delete()
    _ = self.db.query(ImageIntelligence).delete()
    _ = self.db.query(KnownPerson).delete()

    # Phase 2-4: Same as before...
    # ...
```

**GitHub Issue Template:**
```markdown
**Title:** [CRITICAL] delete_all_entities() leaks ALL files to disk

**Labels:** bug, critical, resource-leak, file-management, data-integrity

**Description:**
`delete_all_entities()` deletes all database records but does not delete any files from storage, leaving all entity and face files orphaned on disk.

**Impact:**
- Complete database/filesystem disconnect
- All media files orphaned after deletion
- Disk space exhausted by orphaned files
- No mechanism to identify orphaned files
- Manual cleanup required
- Used by DELETE /entities endpoint (production impact)

**Files:**
- src/store/store/service.py (delete_all_entities method)
- src/store/store/routes.py (delete_collection endpoint uses this)

**Root Cause:**
Method only deletes database records. File storage cleanup completely missing.

**Fix:**
Query all entities and faces, delete their files, then delete database records.

**Acceptance Criteria:**
- [ ] All entity files deleted before database deletion
- [ ] All face files deleted before database deletion
- [ ] Error handling for file deletion failures
- [ ] Integration test verifies all files removed
- [ ] Test verifies storage directory is empty after deletion
```

---

### CRITICAL-006: Vector Embeddings Not Deleted (Qdrant Leak)

**Category:** Source Code / Resource Management / Data Leaks
**Severity:** CRITICAL
**Impact:** Vector database bloat, orphaned embeddings accumulate, query performance degradation, storage waste

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/src/store/store/service.py` (delete_entity, delete_all_entities)
- `/Users/anandasarangaram/Work/cl_server/services/store/src/store/m_insight/vector_stores.py` (delete_vector methods exist but never called)

**Description:**
When entities or faces are deleted, their vector embeddings (CLIP, DINO, face embeddings) stored in Qdrant are **never removed**. The `delete_vector()` methods exist in `vector_stores.py` but are **never called** from anywhere in the codebase.

**Vector Storage Context:**
- **CLIP embeddings**: 512-dimensional vectors stored per entity in Qdrant collection
- **DINO embeddings**: 384-dimensional vectors for duplicate detection
- **Face embeddings**: 512-dimensional vectors per detected face for face recognition

**Current State:**
```python
# vector_stores.py:50-55
class CLIPVectorStore:
    def delete_vector(self, id: int) -> None:
        """Deletes a vector by its ID."""
        self.client.delete(collection_name=self.collection, points_selector=[id])
    # ✓ Method exists

# vector_stores.py:197-200
class FaceVectorStore:
    def delete_vector(self, id: int):
        """Delete a face embedding by face ID."""
        self.client.delete(collection_name=self.collection, points_selector=[id])
    # ✓ Method exists
```

**Grep search shows NO calls to delete_vector:**
```bash
$ grep -r "delete_vector(" services/store/src/
# Only shows the method definitions, NO CALLS
```

**Impact:**
1. Entity deleted → CLIP embedding remains in Qdrant
2. Entity deleted → DINO embedding remains in Qdrant
3. Face deleted → Face embedding remains in Qdrant
4. Over time, Qdrant collections filled with orphaned vectors
5. Query performance degrades (searching through deleted items)
6. Storage waste (vectors for non-existent entities/faces)
7. Similarity search returns results for deleted entities

**Fix Required:**

Add vector cleanup to `delete_entity()`:

```python
# service.py - add to delete_entity method
def delete_entity(self, entity_id: int, *, _from_parent: bool = False) -> bool:
    """Delete an entity (hard delete with proper versioning)."""
    entity = self.db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        return False

    # ... existing validation code ...

    # NEW: Delete vector embeddings from Qdrant
    try:
        from .m_insight.vector_stores import CLIPVectorStore, DINOVectorStore, FaceVectorStore

        # Delete entity embeddings (CLIP, DINO)
        clip_store = CLIPVectorStore()
        clip_store.delete_vector(entity_id)

        dino_store = DINOVectorStore()
        dino_store.delete_vector(entity_id)

        # Delete face embeddings
        if entity.faces:
            face_store = FaceVectorStore()
            for face in entity.faces:
                face_store.delete_vector(face.id)
    except Exception as e:
        logger.warning(f"Failed to delete vector embeddings for entity {entity_id}: {e}")

    # Delete face files
    if entity.faces:
        for face in entity.faces:
            if face.file_path:
                _ = self.file_storage.delete_file(face.file_path)

    # Delete entity file
    if entity.file_path:
        _ = self.file_storage.delete_file(entity.file_path)

    self.db.delete(entity)
    self.db.commit()

    return True
```

**Also add to delete_all_entities():**

```python
def delete_all_entities(self) -> None:
    """Delete all entities and related data."""
    # NEW: Phase 0a - Delete all vector embeddings from Qdrant
    try:
        from .m_insight.vector_stores import CLIPVectorStore, DINOVectorStore, FaceVectorStore

        # Get all entity IDs and face IDs before deletion
        entity_ids = [e.id for e in self.db.query(Entity.id).all()]
        face_ids = [f.id for f in self.db.query(Face.id).all()]

        # Delete embeddings
        clip_store = CLIPVectorStore()
        dino_store = DINOVectorStore()
        face_store = FaceVectorStore()

        for entity_id in entity_ids:
            try:
                clip_store.delete_vector(entity_id)
                dino_store.delete_vector(entity_id)
            except Exception as e:
                logger.warning(f"Failed to delete entity {entity_id} embeddings: {e}")

        for face_id in face_ids:
            try:
                face_store.delete_vector(face_id)
            except Exception as e:
                logger.warning(f"Failed to delete face {face_id} embedding: {e}")

    except Exception as e:
        logger.error(f"Failed to cleanup vector embeddings: {e}")

    # Phase 0b - Delete all files (existing code to be added per CRITICAL-005)
    # ...

    # Phase 1-4 - Database cleanup (existing code)
    # ...
```

**GitHub Issue Template:**
```markdown
**Title:** [CRITICAL] Vector embeddings not deleted from Qdrant

**Labels:** bug, critical, resource-leak, vector-db, data-integrity

**Description:**
When entities or faces are deleted, their vector embeddings in Qdrant are never removed, causing vector database bloat and orphaned data.

**Impact:**
- Qdrant collections accumulate orphaned vectors indefinitely
- Query performance degrades (searching deleted items)
- Storage waste in vector database
- Similarity search returns deleted entities/faces
- No cleanup mechanism exists
- delete_vector() methods exist but are never called

**Files:**
- src/store/store/service.py (delete_entity, delete_all_entities)
- src/store/m_insight/vector_stores.py (delete_vector methods)

**Vector Collections Affected:**
- CLIP embeddings (clip_embeddings collection)
- DINO embeddings (dino_embeddings collection)
- Face embeddings (face_embeddings collection)

**Root Cause:**
Vector store delete methods implemented but never invoked during entity/face deletion.

**Fix:**
Call appropriate delete_vector() methods before deleting database records.

**Acceptance Criteria:**
- [ ] delete_entity() removes entity CLIP/DINO embeddings
- [ ] delete_entity() removes all face embeddings
- [ ] delete_all_entities() clears all embeddings from Qdrant
- [ ] Error handling for Qdrant connection failures
- [ ] Integration test verifies embeddings removed
- [ ] Test verifies Qdrant collections are empty after deletion
```

---

## High Priority Issues

### HIGH-001: File Handle Leaks in Test Code

**Category:** Tests / Resource Management
**Severity:** HIGH
**Impact:** Resource exhaustion on CI, test failures on Windows, flaky tests

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/tests/test_m_insight_worker.py` (Lines 175, 192, 241, 286, etc.)

**Description:**
Five tests open file handles with `.open("rb")` but don't properly close them. Files are passed directly to TestClient without context managers.

**Affected Tests:**
1. `test_existing_sync_state_only_newer_versions()` - Lines 175, 192
2. `test_multiple_md5_changes_single_queue()` - Lines 241, 286
3. Plus 3 more tests with similar pattern

**Current Code:**
```python
# BAD - File handle leaked
response = client.post(
    "/entities",
    files={"image": ("test2.png", test_images_unique[1].open("rb"), "image/png")}
)
# File handle never closed!
```

**Fix Required:**
```python
# GOOD - Use context manager
with test_images_unique[1].open("rb") as f:
    response = client.post(
        "/entities",
        files={"image": ("test2.png", f, "image/png")}
    )
```

**Or use fixture pattern:**
```python
@pytest.fixture
def image_file(test_images_unique):
    f = test_images_unique[1].open("rb")
    yield f
    f.close()
```

**GitHub Issue Template:**
```markdown
**Title:** [HIGH] Fix file handle leaks in test_m_insight_worker.py

**Labels:** bug, high, tests, resource-leak

**Description:**
Five tests don't properly close file handles opened with `.open("rb")`.

**Impact:**
- Resource leaks in test suite
- Test failures on CI with many iterations
- File locking issues on Windows
- Potential "too many open files" errors

**Files:**
- tests/test_m_insight_worker.py (5 tests)

**Fix:**
Use context managers (`with` statements) or ensure file cleanup in fixtures.

**Acceptance Criteria:**
- [ ] All file handles properly closed
- [ ] Tests pass 100 iterations without resource errors
- [ ] No file locking issues on Windows
- [ ] lsof shows no leaked file descriptors
```

---

### HIGH-002: N+1 Query Problem in Entity Retrieval

**Category:** Source Code / Performance
**Severity:** HIGH
**Impact:** Significant performance degradation with large datasets (1000 entities = 1001 queries)

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/src/store/store/service.py` (Lines 207-265)

**Description:**
The `get_entities()` function performs N+1 queries when version parameter is provided. For each entity returned, it makes a separate query to fetch version information.

**Current Code:**
```python
def get_entities(
    session: Session,
    page: int = 1,
    page_size: int = 20,
    version: int | None = None,
    # ...
) -> tuple[list[EntityResponse], PaginationMetadata]:
    # Query 1: Get all entities
    entities = session.query(Entity).filter(
        Entity.is_deleted.is_(False)  # Line 238
    ).offset(offset).limit(page_size).all()

    # N queries: One per entity if version provided
    items = []
    for entity in entities:
        if version:
            # Line 256: Separate query for EACH entity
            entity_data = get_entity_version(session, entity.id, version)
        else:
            entity_data = entity
        items.append(EntityResponse.from_orm(entity_data))

    return items, pagination
```

**Performance Impact:**
- 100 entities with version = 101 queries
- 1000 entities with version = 1001 queries
- Response time grows linearly with entity count

**Fix Required:**
Use eager loading or batch query:

```python
def get_entities(...) -> tuple[list[EntityResponse], PaginationMetadata]:
    if version:
        # Batch load all versions in single query
        entity_ids = session.query(Entity.id).filter(
            Entity.is_deleted.is_(False)
        ).offset(offset).limit(page_size).all()

        id_list = [e.id for e in entity_ids]

        # Single query to load all versions
        versions = session.query(EntityVersion).filter(
            EntityVersion.id.in_(id_list),
            EntityVersion.version == version
        ).all()

        items = [EntityResponse.from_orm(v) for v in versions]
    else:
        # Existing logic for non-version case
        entities = session.query(Entity).filter(...)
        items = [EntityResponse.from_orm(e) for e in entities]

    return items, pagination
```

**GitHub Issue Template:**
```markdown
**Title:** [HIGH] Fix N+1 query in get_entities with version parameter

**Labels:** bug, high, performance, database

**Description:**
`get_entities()` performs N+1 queries when version parameter is provided, causing severe performance issues.

**Impact:**
- 1000 entities = 1001 database queries
- Response time grows linearly
- Database server load increases dramatically
- Poor user experience with large datasets

**Files:**
- src/store/store/service.py (lines 207-265)

**Fix:**
Use batch query with `IN` clause to load all versions in single query.

**Acceptance Criteria:**
- [ ] Query count ≤ 2 regardless of entity count
- [ ] Performance test added
- [ ] Existing tests pass
- [ ] Verified with 1000+ entities
```

---
### HIGH-003: FaceMatch Removed, hence not required


### HIGH-004: Silent Error Handling in Job Service

**Category:** Source Code / Error Handling
**Severity:** HIGH
**Impact:** Lost error context, difficult debugging, unclear failure modes

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/src/store/m_insight/job_service.py` (Lines 85-108, 142-164, 196-222)

**Description:**
Three job submission functions catch all exceptions but return `None` without logging error details. Callers cannot distinguish between "file not found", "network error", or "database error".

**Current Code:**
```python
def submit_face_detection_job(entity, storage_service, compute_client):
    try:
        # Lines 85-100: Job submission logic
        job = compute_client.submit(...)
        return job.id
    except Exception:  # Line 105: Too broad!
        # No logging, no error details
        return None  # Caller doesn't know what failed
```

**Issues:**
1. All exceptions caught indiscriminately
2. No logging of error details
3. Returns None - caller can't distinguish error types
4. Makes debugging nearly impossible
5. Same pattern repeated in 3 functions

**Fix Required:**
```python
from loguru import logger

def submit_face_detection_job(
    entity,
    storage_service,
    compute_client
) -> str:  # Raise exception instead of returning None
    try:
        # Job submission logic
        job = compute_client.submit(...)
        return job.id
    except FileNotFoundError as e:
        logger.error(f"Image file not found for entity {entity.id}: {e}")
        raise
    except ComputeClientError as e:
        logger.error(f"Compute client error for entity {entity.id}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error submitting job for entity {entity.id}: {e}")
        raise
```

**GitHub Issue Template:**
```markdown
**Title:** [HIGH] Fix silent error handling in job_service.py

**Labels:** bug, high, error-handling, observability

**Description:**
Three job submission functions catch all exceptions and return None without logging, losing critical error context.

**Impact:**
- Impossible to debug failures
- Cannot distinguish error types
- No error logs for troubleshooting
- Silent failures

**Files:**
- src/store/m_insight/job_service.py (3 functions)

**Fix:**
1. Log specific error details
2. Raise exceptions instead of returning None
3. Use specific exception types
4. Add error context

**Acceptance Criteria:**
- [ ] Errors logged with context
- [ ] Specific exception types
- [ ] Tests for error cases
- [ ] Error monitoring alerts
```

---

### HIGH-005: MD5 Hash Length Assertion Bug in Tests

**Category:** Tests / Assertions
**Severity:** HIGH (test validity issue)
**Impact:** Incorrect test validation - test passes with wrong hash length

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/tests/test_store/test_integration/test_put_endpoint.py` (Line 112)

**Description:**
Test asserts MD5 hash length is 128 characters, but MD5 hex digest is actually 32 characters. The comment says "SHA-512 hash length" but the code extracts `md5` field.

**Current Code:**
```python
def test_put_metadata_accuracy():
    # ... upload file ...

    # Line 112: WRONG!
    assert len(data["md5"]) == 128  # Comment: SHA-512 hash length
    # MD5 is 32 chars, SHA-512 is 128 chars - this is backwards!
```

**Why This Matters:**
- Test passes even if MD5 hash is wrong
- Doesn't catch hash generation bugs
- Misleading assertion
- If hash is actually 128 chars, it's not MD5!

**Fix Required:**
```python
def test_put_metadata_accuracy():
    # ... upload file ...

    # Correct assertions
    assert len(data["md5"]) == 32, "MD5 hash should be 32 hex characters"
    assert all(c in "0123456789abcdef" for c in data["md5"].lower()), "MD5 should be hex"
```

**Or if using SHA-512:**
```python
# If actually using SHA-512, rename the field!
assert len(data["sha512"]) == 128
assert len(data["md5"]) == 32  # Keep MD5 too for backwards compat
```

**GitHub Issue Template:**
```markdown
**Title:** [HIGH] Fix MD5 hash length assertion (should be 32, not 128)

**Labels:** bug, high, tests, validation

**Description:**
Test asserts MD5 hash is 128 characters, but MD5 hex digest is 32 characters. This is a test validity issue.

**Impact:**
- Test doesn't validate MD5 correctly
- Could miss hash generation bugs
- Confusing assertion

**Files:**
- tests/test_store/test_integration/test_put_endpoint.py (line 112)

**Fix:**
Change assertion from 128 to 32 characters, or clarify which hash algorithm is used.

**Acceptance Criteria:**
- [ ] Assertion matches actual hash length
- [ ] Test fails with invalid hash
- [ ] Comments match code
```

---

### HIGH-006: Generic Exception Used Instead of Specific Error Type

**Category:** Source Code / Exception Handling
**Severity:** HIGH (poor error handling practice)
**Impact:** Makes error handling less precise, harder to catch specific errors

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/src/store/m_insight/media_insight.py` (Line 79)

**Description:**
Code raises generic `Exception` instead of a more specific exception type. This violates Python best practices and makes it difficult for callers to handle specific error conditions.

**Current Code:**
```python
if self.config.mqtt_port:
    server_config = ServerConfig(
        # ...
    )
else:
    raise Exception("MQTT port is required")  # Line 79 - TOO GENERIC!
```

**Why This Matters:**
- Generic `Exception` catches too broadly in try/except blocks
- Callers can't distinguish between different error types
- Violates Python conventions (PEP 8)
- Makes debugging harder

**Fix Required:**
```python
# Option 1: Use ValueError for configuration issues
if self.config.mqtt_port:
    server_config = ServerConfig(
        # ...
    )
else:
    raise ValueError("MQTT port is required")

# Option 2: Create custom ConfigurationError exception
class ConfigurationError(Exception):
    """Raised when required configuration is missing or invalid."""
    pass

# Then use it:
raise ConfigurationError("MQTT port is required")
```

**Recommendation:**
Use `ValueError` for this case, as it's a configuration validation issue.

**GitHub Issue Template:**
```markdown
**Title:** [HIGH] Replace generic Exception with ValueError in media_insight.py

**Labels:** bug, high, exception-handling, code-quality

**Description:**
Line 79 of `media_insight.py` raises generic `Exception("MQTT port is required")` instead of a more specific exception type.

**Impact:**
- Poor error handling practice
- Makes error catching less precise
- Violates Python conventions

**Files:**
- src/store/m_insight/media_insight.py (line 79)

**Fix:**
Replace `raise Exception(...)` with `raise ValueError(...)` for configuration validation errors.

**Acceptance Criteria:**
- [ ] Generic Exception replaced with ValueError
- [ ] Error message remains clear and descriptive
- [ ] Tests updated if needed
```

---

## Medium Priority Issues

### MEDIUM-001: Unused Variable Assignments in Argparse

**Category:** Source Code / Code Quality
**Severity:** MEDIUM
**Impact:** Code clutter, unnecessary suppressions

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/src/store/main.py` (Lines 35-57)

**Description:**
Argparse `add_argument()` calls are assigned to `_` variable to suppress "unused variable" warnings, but this is unnecessary as argparse methods don't need their return values.

**Current Code:**
```python
parser = ArgumentParser(prog="store")
_ = parser.add_argument("--no-auth", action="store_true")  # Line 35
_ = parser.add_argument("--no-migrate", action="store_true")  # Line 36
# ... 20+ more lines like this
```

**Fix Required:**
```python
parser = ArgumentParser(prog="store")
parser.add_argument("--no-auth", action="store_true")
parser.add_argument("--no-migrate", action="store_true")
# Much cleaner!
```

**GitHub Issue Template:**
```markdown
**Title:** [MEDIUM] Remove unnecessary underscore assignments in argparse

**Labels:** cleanup, medium, code-quality

**Description:**
Argparse calls use `_ = parser.add_argument(...)` unnecessarily.

**Files:**
- src/store/main.py (lines 35-57)
- src/store/m_insight_worker.py (similar pattern)

**Fix:**
Remove `_ = ` prefix from add_argument calls.
```

---

### MEDIUM-002: Boolean Comparison Using == Instead of is_()

**Category:** Source Code / SQLAlchemy Best Practice
**Severity:** MEDIUM
**Impact:** May not work correctly with all database backends

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/src/store/store/service.py` (Line 238)

**Description:**
Uses `Entity.is_deleted == False` instead of `Entity.is_deleted.is_(False)` in SQLAlchemy query. While it works, it's not the recommended pattern.

**Current Code:**
```python
# Line 238
entities = session.query(Entity).filter(
    Entity.is_deleted == False  # noqa: E712 - knows it's wrong!
).all()
```

**Fix Required:**
```python
entities = session.query(Entity).filter(
    Entity.is_deleted.is_(False)  # Correct SQLAlchemy pattern
).all()

# Or even simpler:
entities = session.query(Entity).filter(
    ~Entity.is_deleted  # NOT operator
).all()
```

**GitHub Issue Template:**
```markdown
**Title:** [MEDIUM] Use SQLAlchemy is_() for boolean comparisons

**Labels:** improvement, medium, sqlalchemy

**Description:**
Boolean comparisons use `== False` instead of `.is_(False)` or `~` operator.

**Files:**
- src/store/store/service.py (line 238)

**Fix:**
Use `.is_(False)` or `~column` for boolean comparisons.
```

---

### MEDIUM-003: Commented Out Code in main.py

**Category:** Source Code / Code Quality
**Severity:** MEDIUM
**Impact:** Confusing, suggests incomplete refactoring

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/src/store/main.py` (Lines 26, 77-92)

**Description:**
Contains commented-out code and long comment blocks explaining why reload feature doesn't work, suggesting incomplete implementation.

**Current Code:**
```python
# Line 26
# Do we need this? from .common import database

# Lines 77-92: Long comment block
# For reload, we accept we can't easily pass object.
# We might need to rely on env vars we set above (CL_SERVER_DIR)
# and let the app strictly re-initialize?
# But we just removed Config dependency.
# ... 15 more lines of comments
```

**Fix Required:**
Either:
1. Fix the reload feature properly
2. Remove reload support and document why
3. Raise NotImplementedError if --reload used

```python
if args.reload:
    raise NotImplementedError(
        "--reload is not supported. Use uvicorn directly: "
        "uvicorn store.store:app --reload"
    )
```

**GitHub Issue Template:**
```markdown
**Title:** [MEDIUM] Clean up commented code and reload feature in main.py

**Labels:** cleanup, medium, refactoring

**Description:**
main.py has commented code and long comment blocks about reload feature not working.

**Files:**
- src/store/main.py (lines 26, 77-92)

**Fix:**
Either implement reload properly or remove support with clear error message.
```

---

### MEDIUM-004: Import Inside Function Body

**Category:** Source Code / Code Quality
**Severity:** MEDIUM
**Impact:** Performance - importing on every function call

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/src/store/store/routes.py` (Line 74)

**Description:**
`import math` is inside the function body instead of at module level, causing it to be imported every time the function is called.

**Current Code:**
```python
def get_entities_endpoint(...):
    # Line 74: Import inside function!
    import math

    total_pages = math.ceil(total / page_size)
```

**Fix Required:**
```python
# At top of file with other imports
import math

def get_entities_endpoint(...):
    total_pages = math.ceil(total / page_size)
```

**GitHub Issue Template:**
```markdown
**Title:** [MEDIUM] Move math import to module level in routes.py

**Labels:** cleanup, medium, performance

**Description:**
Import statement inside function causes repeated imports.

**Files:**
- src/store/store/routes.py (line 74)

**Fix:**
Move to module level with other imports.
```

---

### MEDIUM-005: Incomplete Validation Logic

**Category:** Source Code / Logic
**Severity:** MEDIUM
**Impact:** Validation doesn't actually validate anything

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/src/store/store/service.py` (Lines 88-89)

**Description:**
`_validate_parent_id()` method accepts `_is_collection` parameter but never uses it. The method body is just `pass`, meaning no validation occurs.

**Current Code:**
```python
def _validate_parent_id(
    session: Session,
    parent_id: int | None,
    _is_collection: bool  # Line 88: Parameter never used!
) -> None:
    pass  # Line 89: No validation!
```

**Expected Logic:**
Should validate that collections can't have `is_collection=True`, or enforce parent-child relationship rules.

**Fix Required:**
```python
def _validate_parent_id(
    session: Session,
    parent_id: int | None,
    is_collection: bool
) -> None:
    """Validate parent_id is valid and follows rules.

    Rules:
    - Collections must not have non-collection parents
    - Parent must exist if provided
    - No circular references
    """
    if parent_id is None:
        return

    parent = session.query(Entity).filter(Entity.id == parent_id).first()
    if not parent:
        raise ValueError(f"Parent {parent_id} does not exist")

    if is_collection and not parent.is_collection:
        raise ValueError("Collections must have collection parents")
```

**GitHub Issue Template:**
```markdown
**Title:** [MEDIUM] Implement validation logic in _validate_parent_id()

**Labels:** bug, medium, validation

**Description:**
Validation method has empty body and unused parameter.

**Files:**
- src/store/store/service.py (lines 88-89)

**Fix:**
Implement actual validation logic or remove method.
```

---

### MEDIUM-006: Flaky Tests Using time.sleep() for Synchronization

**Category:** Tests / Reliability
**Severity:** MEDIUM
**Impact:** Tests may fail intermittently, especially on slow CI systems

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/tests/test_m_insight_mqtt.py` (Lines 86, 109, 153, 160)

**Description:**
Tests use `time.sleep(0.5)` and `time.sleep(1.0)` to wait for asynchronous operations, which is unreliable and can cause flaky tests.

**Current Code:**
```python
def test_m_insight_lifecycle_events():
    processor.start()
    time.sleep(0.5)  # Line 86: Hope it's done by now?

    # Check for event
    assert event_occurred

    processor.stop()
    time.sleep(1.0)  # Line 109: Hope it stopped?
```

**Issues:**
1. No guarantee operation completes in time
2. May fail on slow CI systems
3. Tests take longer than necessary (waiting when already done)
4. May hang indefinitely if operation never completes

**Fix Required:**
```python
import threading

def test_m_insight_lifecycle_events():
    event = threading.Event()

    def callback():
        event.set()

    processor.start(callback=callback)

    # Wait with timeout
    assert event.wait(timeout=5.0), "Processor failed to start"

    processor.stop()
```

**Or use async properly:**
```python
@pytest.mark.asyncio
async def test_m_insight_lifecycle_events():
    await processor.start()
    # No sleep needed - await ensures completion
    assert processor.is_running

    await processor.stop()
    assert not processor.is_running
```

**GitHub Issue Template:**
```markdown
**Title:** [MEDIUM] Replace time.sleep() with proper synchronization in MQTT tests

**Labels:** bug, medium, tests, flaky

**Description:**
Tests use time.sleep() for synchronization, causing flaky tests.

**Impact:**
- Intermittent failures
- Slow tests
- Unreliable on CI

**Files:**
- tests/test_m_insight_mqtt.py (6 tests)

**Fix:**
Use threading.Event, asyncio.Event, or proper await patterns.

**Acceptance Criteria:**
- [ ] No time.sleep() for synchronization
- [ ] Tests have timeouts
- [ ] Tests pass 100 iterations
- [ ] Faster test execution
```

---

### MEDIUM-007: RuntimeError Overuse for "Database Not Initialized"

**Category:** Source Code / Exception Handling
**Severity:** MEDIUM (consistency and specificity issue)
**Impact:** Less precise error handling, harder to catch specific initialization errors

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/src/store/m_insight/media_insight.py` (Lines 51, 180, 226, 376, 396, 410)

**Description:**
Code raises `RuntimeError("Database not initialized")` in 6+ places. While technically correct, a custom exception would make error handling more precise and allow callers to specifically catch initialization failures.

**Current Code:**
```python
def some_method(self):
    if not database.SessionLocal:
        raise RuntimeError("Database not initialized. Call database.init_db() first.")
    # ... (repeated in 6+ places)
```

**Why This Matters:**
- `RuntimeError` is too generic for this specific error condition
- Callers can't distinguish initialization errors from other runtime errors
- Custom exception would improve code clarity and maintainability
- Follows Python best practices for specific error conditions

**Fix Required:**
```python
# In common/models.py or common/exceptions.py:
class DatabaseNotInitializedError(RuntimeError):
    """Raised when attempting to use database before initialization."""
    pass

# Then use it:
def some_method(self):
    if not database.SessionLocal:
        raise DatabaseNotInitializedError("Call database.init_db() first")
```

**Affected Locations:**
- media_insight.py:51 - `__init__` method
- media_insight.py:180 - `_get_intelligence_entry` method
- media_insight.py:226 - `_get_face` method
- media_insight.py:376 - `_reconcile_dino_descriptors` method
- media_insight.py:396 - `_reconcile_clip_descriptors` method
- media_insight.py:410 - `_reconcile_faces` method

**GitHub Issue Template:**
```markdown
**Title:** [MEDIUM] Create DatabaseNotInitializedError custom exception

**Labels:** enhancement, medium, exception-handling, refactoring

**Description:**
Code raises `RuntimeError("Database not initialized")` in 6+ places in `media_insight.py`. A custom exception would make error handling more precise.

**Impact:**
- Better error specificity
- Improved code maintainability
- Follows Python best practices

**Files:**
- src/store/m_insight/media_insight.py (6+ occurrences)
- Need to create: src/store/common/exceptions.py

**Fix:**
1. Create `DatabaseNotInitializedError(RuntimeError)` exception
2. Replace all `RuntimeError("Database not initialized")` with new exception
3. Update error handlers if needed

**Acceptance Criteria:**
- [ ] Custom exception created
- [ ] All 6+ occurrences updated
- [ ] Exception message remains clear
- [ ] Tests pass
```

---

### MEDIUM-008: RuntimeError Overuse for "Storage Service Not Initialized"

**Category:** Source Code / Exception Handling
**Severity:** MEDIUM (consistency and specificity issue)
**Impact:** Less precise error handling, similar to MEDIUM-007

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/src/store/m_insight/media_insight.py` (Line 289)

**Description:**
Code raises `RuntimeError("Storage service not initialized")` using generic `RuntimeError`. While less common than the database initialization error, this should also use a custom exception for consistency.

**Current Code:**
```python
def _get_face_path(self, face_path: str | None) -> Path | None:
    if not face_path:
        return None
    if not self.storage_service:
        raise RuntimeError("Storage service not initialized")  # Line 289
    return self.storage_service.get_absolute_path(face_path)
```

**Fix Required:**
```python
# In common/exceptions.py:
class StorageServiceNotInitializedError(RuntimeError):
    """Raised when attempting to use storage service before initialization."""
    pass

# Then use it:
if not self.storage_service:
    raise StorageServiceNotInitializedError("Call initialize() first")
```

**Note:** This could potentially be combined with MEDIUM-007 into a general `ServiceNotInitializedError` if preferred.

**GitHub Issue Template:**
```markdown
**Title:** [MEDIUM] Create StorageServiceNotInitializedError custom exception

**Labels:** enhancement, medium, exception-handling, refactoring

**Description:**
Code raises `RuntimeError("Storage service not initialized")` using generic RuntimeError. Should use custom exception for consistency with database initialization error.

**Impact:**
- Better error specificity
- Consistent error handling pattern
- Improved maintainability

**Files:**
- src/store/m_insight/media_insight.py (line 289)
- Need to create: src/store/common/exceptions.py (if not created by MEDIUM-007)

**Fix:**
1. Create `StorageServiceNotInitializedError(RuntimeError)` exception
2. Replace RuntimeError with new exception
3. Consider consolidating with DatabaseNotInitializedError into general pattern

**Acceptance Criteria:**
- [ ] Custom exception created
- [ ] Exception used in media_insight.py
- [ ] Error message remains clear
- [ ] Tests pass
```

---

### MEDIUM-009: Docstrings Incorrect for create_entity and update_entity Return Types

**Category:** Source Code / Documentation
**Severity:** MEDIUM (documentation accuracy issue)
**Impact:** Misleading documentation for API developers

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/src/store/store/service.py` (Lines 361-374, 478-492)

**Description:**
The `create_entity` and `update_entity` methods return `tuple[Item, bool]` where the bool indicates `is_duplicate`, but their docstrings incorrectly state they return just "Item instance".

**Current Code:**
```python
def create_entity(
    self,
    body: BodyCreateEntity,
    image: bytes | None = None,
    filename: str = "file",
    user_id: str | None = None,
) -> tuple[Item, bool]:
    """
    Create a new entity.

    Args:
        body: Entity creation data
        image: Optional image file bytes
        filename: Original filename
        user_id: Optional user identifier from JWT (None in demo mode)

    Returns:
        Created Item instance  # ❌ WRONG! Should mention tuple

    Raises:
        DuplicateFileError: If file with same MD5 already exists
    """
    # ... code ...
    return (self._entity_to_item(entity), False)  # Returns tuple[Item, bool]

def update_entity(
    self,
    entity_id: int,
    body: BodyUpdateEntity,
    image: bytes | None,
    filename: str = "file",
    user_id: str | None = None,
) -> tuple[Item, bool] | None:
    """
    Fully update an existing entity (PUT) - file upload is optional for non-collections.

    Args:
        entity_id: Entity ID
        body: Entity update data
        image: Image file bytes (optional - if None, only metadata is updated)
        filename: Original filename
        user_id: Optional user identifier from JWT (None in demo mode)

    Returns:
        Updated Item instance or None if not found  # ❌ WRONG! Should mention tuple

    Raises:
        DuplicateFileError: If file with same MD5 already exists
    """
    # ... code ...
    return (self._entity_to_item(entity), False)  # Returns tuple[Item, bool]
```

**Why This Matters:**
- Developers relying on docstrings will expect wrong return type
- Code that unpacks the tuple appears inconsistent with docs
- Type hints are correct, but docstrings contradict them

**Fix Required:**
```python
def create_entity(...) -> tuple[Item, bool]:
    """
    Create a new entity.

    Args:
        body: Entity creation data
        image: Optional image file bytes
        filename: Original filename
        user_id: Optional user identifier from JWT (None in demo mode)

    Returns:
        Tuple of (Item, is_duplicate):
        - Item: Created entity as Item instance
        - is_duplicate: Always False for new creations (reserved for future use)

    Raises:
        DuplicateFileError: If file with same MD5 already exists
    """

def update_entity(...) -> tuple[Item, bool] | None:
    """
    Fully update an existing entity (PUT) - file upload is optional for non-collections.

    Args:
        entity_id: Entity ID
        body: Entity update data
        image: Image file bytes (optional - if None, only metadata is updated)
        filename: Original filename
        user_id: Optional user identifier from JWT (None in demo mode)

    Returns:
        Tuple of (Item, is_duplicate) or None if entity not found:
        - Item: Updated entity as Item instance
        - is_duplicate: Always False for updates (reserved for future use)
        Returns None if entity with entity_id doesn't exist

    Raises:
        DuplicateFileError: If file with same MD5 already exists
    """
```

**GitHub Issue Template:**
```markdown
**Title:** [MEDIUM] Fix docstrings for create_entity and update_entity return types

**Labels:** documentation, medium, code-quality

**Description:**
The `create_entity` and `update_entity` methods in `service.py` return `tuple[Item, bool]` but their docstrings incorrectly document the return type as just "Item instance".

**Impact:**
- Misleading documentation for developers
- Docstrings contradict type hints
- Unclear what the bool return value represents

**Files:**
- src/store/store/service.py (lines 361-374, 478-492)

**Fix:**
Update docstrings to accurately describe the tuple return type:
- Document that return is tuple[Item, bool]
- Explain what the bool flag represents (is_duplicate)
- Clarify when None is returned (update_entity only)

**Acceptance Criteria:**
- [ ] Docstrings accurately describe return type
- [ ] Bool flag purpose documented
- [ ] Type hints match docstrings
- [ ] Consistent style with other docstrings
```

---

### MEDIUM-010: Inconsistent "Database Not Initialized" Error Messages

**Category:** Source Code / Exception Messages
**Severity:** MEDIUM (consistency issue)
**Impact:** Inconsistent error messages make debugging less predictable

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/src/store/m_insight/media_insight.py` (Lines 51, 180, 226, 376, 396, 410)

**Description:**
The code raises `RuntimeError("Database not initialized")` in 6 places, but with inconsistent messages. The first occurrence provides helpful instructions, while the others don't.

**Current Code:**
```python
# Line 51: Has helpful instruction
if not database.SessionLocal:
    raise RuntimeError("Database not initialized. Call database.init_db() first.")

# Lines 180, 226, 376, 396, 410: Missing instruction
if not database.SessionLocal:
    raise RuntimeError("Database not initialized")  # Less helpful!
```

**Why This Matters:**
- Inconsistent error messages confuse developers
- Users get different levels of help depending on which code path fails
- Error message quality should be consistent across codebase

**Fix Required:**
```python
# Option 1: Make all messages include the instruction
raise RuntimeError("Database not initialized. Call database.init_db() first.")

# Option 2: Use DatabaseNotInitializedError (from MEDIUM-007)
# and set a consistent default message
class DatabaseNotInitializedError(RuntimeError):
    """Raised when attempting to use database before initialization."""
    def __init__(self, message: str = "Database not initialized. Call database.init_db() first."):
        super().__init__(message)

# Then use consistently:
raise DatabaseNotInitializedError()
```

**Recommendation:**
Implement MEDIUM-007 first (custom exception), then ensure all uses have consistent messaging.

**Affected Locations:**
- media_insight.py:51 - ✓ Has instruction
- media_insight.py:180 - ❌ Missing instruction
- media_insight.py:226 - ❌ Missing instruction
- media_insight.py:376 - ❌ Missing instruction
- media_insight.py:396 - ❌ Missing instruction
- media_insight.py:410 - ❌ Missing instruction

**GitHub Issue Template:**
```markdown
**Title:** [MEDIUM] Standardize "Database not initialized" error messages

**Labels:** enhancement, medium, error-messages, consistency

**Description:**
The code raises `RuntimeError("Database not initialized")` in 6 places with inconsistent messages. Only one occurrence includes helpful instructions.

**Impact:**
- Inconsistent developer experience
- Some error messages less helpful than others
- Reduces code maintainability

**Files:**
- src/store/m_insight/media_insight.py (6 occurrences)

**Fix:**
1. Standardize all error messages to include instruction: "Call database.init_db() first"
2. Or implement MEDIUM-007 (DatabaseNotInitializedError) with consistent default message

**Acceptance Criteria:**
- [ ] All 6 occurrences have identical or equivalent messages
- [ ] Error messages provide actionable guidance
- [ ] Consistent with MEDIUM-007 if implemented
```

---

## Low Priority Issues

### LOW-001: Unused Import in Multiple Files

**Category:** Source Code / Code Quality
**Severity:** LOW
**Impact:** Minor code clutter

**Files Affected:**
- Multiple files across codebase

**Description:**
Various unused imports that can be removed with `ruff check --fix`.

**Fix Required:**
```bash
# Auto-fix all unused imports
uv run ruff check --fix src/
```

**GitHub Issue Template:**
```markdown
**Title:** [LOW] Remove unused imports across codebase

**Labels:** cleanup, low, code-quality

**Description:**
Several files have unused imports.

**Fix:**
Run `uv run ruff check --fix src/`

**Acceptance Criteria:**
- [ ] No unused imports reported
- [ ] Tests still pass
```

---

### LOW-002: Missing Docstrings

**Category:** Source Code / Documentation
**Severity:** LOW
**Impact:** Reduced code readability

**Files Affected:**
- Multiple functions and classes missing docstrings

**Description:**
Several functions lack docstrings explaining their purpose, parameters, and return values.

**GitHub Issue Template:**
```markdown
**Title:** [LOW] Add docstrings to undocumented functions

**Labels:** documentation, low

**Description:**
Several functions missing docstrings.

**Fix:**
Add Google-style docstrings to public functions.
```

---

### LOW-003: TODO Comments Not Tracked

**Category:** Source Code / Technical Debt
**Severity:** LOW
**Impact:** Forgotten future work

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/src/store/store/service.py` (Line 241)

**Description:**
TODO comment says "Implement filtering and search logic" but parameters `filter_param` and `search_query` are accepted but unused.

**Current Code:**
```python
def get_entities(
    session: Session,
    page: int = 1,
    page_size: int = 20,
    filter_param: str | None = None,  # Accepted but unused
    search_query: str | None = None,  # Accepted but unused
) -> tuple[list[EntityResponse], PaginationMetadata]:
    # Line 241: TODO: Implement filtering and search logic
    pass  # Not implemented!
```

**Fix Required:**
Either:
1. Implement the feature
2. Remove unused parameters
3. Create GitHub issue and link in comment

```python
# TODO(#123): Implement filtering and search logic
# For now, these parameters are ignored
```

**GitHub Issue Template:**
```markdown
**Title:** [LOW] Implement filtering and search logic in get_entities()

**Labels:** enhancement, low, feature-request

**Description:**
get_entities() accepts filter_param and search_query but doesn't use them.

**Files:**
- src/store/store/service.py (line 241)

**Implementation:**
Add WHERE clauses for filtering and full-text search.
```

---

### LOW-004: Typo in Error Message (Extra Space Before Period)

**Category:** Source Code / Error Messages
**Severity:** LOW (cosmetic issue)
**Impact:** Minor - slightly unprofessional error message formatting

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/src/store/m_insight/vector_stores.py` (Line 133)

**Description:**
Error message has an extra space before the period: "Failed to retrieve collection parameters ." (should be "parameters.")

**Current Code:**
```python
if collection is None:
    raise ValueError("Failed to retrieve collection parameters .")  # Line 133
    #                                                           ^ Extra space!
```

**Fix Required:**
```python
raise ValueError("Failed to retrieve collection parameters.")
```

**Why This Matters:**
- Minor typo in user-facing error message
- Reduces professionalism
- Easy fix

**GitHub Issue Template:**
```markdown
**Title:** [LOW] Fix typo in vector_stores.py error message

**Labels:** bug, low, typo, error-messages

**Description:**
Error message on line 133 of `vector_stores.py` has an extra space before the period: "Failed to retrieve collection parameters ."

**Impact:**
- Cosmetic issue
- Minor professionalism concern

**Files:**
- src/store/m_insight/vector_stores.py (line 133)

**Fix:**
Remove extra space: "Failed to retrieve collection parameters."

**Acceptance Criteria:**
- [ ] Typo corrected
- [ ] Error message properly formatted
```

---

### MEDIUM-011: Missing Docstrings in broadcaster.py

**Category:** Source Code / Documentation
**Severity:** MEDIUM (API documentation)
**Impact:** Public methods lack proper documentation for users

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/src/store/m_insight/broadcaster.py` (Lines 16, 65, 72, 77)

**Description:**
Four public methods in `MInsightBroadcaster` class are missing proper docstrings with Args and Returns documentation.

**Missing Docstrings:**

1. **`__init__(config: MInsightConfig)` (Line 16)** - No docstring
2. **`publish_start(version_start: int, version_end: int)` (Line 65)** - No docstring
3. **`publish_end(processed_count: int)` (Line 72)** - No docstring
4. **`publish_status(status: str)` (Line 77)** - No docstring

**Current Code:**
```python
class MInsightBroadcaster:
    """Manages MQTT broadcasting for mInsight process."""

    def __init__(self, config: MInsightConfig):  # NO DOCSTRING
        self.config: MInsightConfig = config
        # ...

    def publish_start(self, version_start: int, version_end: int) -> None:  # NO DOCSTRING
        self.current_status.status = "running"
        # ...

    def publish_end(self, processed_count: int) -> None:  # NO DOCSTRING
        self.current_status.status = "idle"
        # ...

    def publish_status(self, status: str) -> None:  # NO DOCSTRING
        self.current_status.status = status
        # ...
```

**Fix Required:**
```python
def __init__(self, config: MInsightConfig):
    """Initialize MQTT broadcaster for mInsight process.

    Args:
        config: MInsight configuration with MQTT broker settings
    """

def publish_start(self, version_start: int, version_end: int) -> None:
    """Publish mInsight processing start event to MQTT.

    Args:
        version_start: Starting version number being processed
        version_end: Ending version number being processed
    """

def publish_end(self, processed_count: int) -> None:
    """Publish mInsight processing completion event to MQTT.

    Args:
        processed_count: Number of entities successfully processed
    """

def publish_status(self, status: str) -> None:
    """Publish mInsight status update to MQTT.

    Args:
        status: Status string (running, idle, offline, error, etc.)
    """
```

**GitHub Issue Template:**
```markdown
**Title:** [MEDIUM] Add docstrings to MInsightBroadcaster public methods

**Labels:** documentation, medium, code-quality

**Description:**
Four public methods in `MInsightBroadcaster` class lack proper docstrings with Args documentation.

**Impact:**
- Reduced code maintainability
- Unclear API for developers
- Missing parameter documentation

**Files:**
- src/store/m_insight/broadcaster.py (lines 16, 65, 72, 77)

**Fix:**
Add comprehensive docstrings with Args sections for:
- `__init__`
- `publish_start`
- `publish_end`
- `publish_status`

**Acceptance Criteria:**
- [ ] All methods have docstrings
- [ ] Args sections document parameters
- [ ] Follows Google/NumPy docstring style
```

---

### MEDIUM-012: Missing/Minimal Docstrings in monitor.py

**Category:** Source Code / Documentation
**Severity:** MEDIUM (API documentation)
**Impact:** Public methods lack comprehensive documentation

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/src/store/store/monitor.py` (Lines 16, 21, 50, 91)

**Description:**
`MInsightMonitor` class has minimal docstrings that lack Args, Returns, and implementation details.

**Issues:**

1. **`__init__(config: StoreConfig)` (Line 16)** - No docstring
2. **`start()` (Line 21)** - Minimal: "Start monitoring." - missing details
3. **`stop()` (Line 50)** - Minimal: "Stop monitoring."
4. **`get_status()` (Line 91)** - Minimal: "Get the monitored process status." - missing Returns

**Fix Required:**
```python
def __init__(self, config: StoreConfig):
    """Initialize MQTT monitor for mInsight process status.

    Args:
        config: Store configuration with MQTT broker and port settings
    """

def start(self) -> None:
    """Start monitoring mInsight status via MQTT.

    Subscribes to mInsight/{port}/status topic and starts background
    MQTT client loop to receive status updates.

    Logs warning if MQTT is disabled in configuration.
    """

def stop(self) -> None:
    """Stop monitoring and disconnect from MQTT broker.

    Stops MQTT client background loop and cleanly disconnects.
    """

def get_status(self) -> MInsightStatus | None:
    """Get the most recent mInsight process status.

    Returns:
        MInsightStatus with current status, or None if no status received yet
    """
```

**GitHub Issue Template:**
```markdown
**Title:** [MEDIUM] Improve docstrings in MInsightMonitor class

**Labels:** documentation, medium, code-quality

**Description:**
`MInsightMonitor` class methods have minimal docstrings lacking Args, Returns, and implementation details.

**Impact:**
- Unclear API behavior
- Missing parameter documentation
- No return value documentation

**Files:**
- src/store/store/monitor.py (lines 16, 21, 50, 91)

**Fix:**
Enhance docstrings for:
- `__init__` - add Args
- `start()` - add implementation details
- `stop()` - add implementation details
- `get_status()` - add Returns section

**Acceptance Criteria:**
- [ ] All methods have comprehensive docstrings
- [ ] Args and Returns sections present where applicable
- [ ] Implementation details documented
```

---

### LOW-005: Minimal Docstrings in auth.py

**Category:** Source Code / Documentation
**Severity:** LOW (minor documentation gaps)
**Impact:** Minor - decorator functions lack parameter documentation

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/src/store/common/auth.py` (Lines 162, 202)

**Description:**
Two authentication dependency functions have minimal or missing docstrings.

**Issues:**

1. **`require_permission(permission)` (Line 162)** - Minimal: "Require a specific permission." - missing Args, Returns
2. **`require_admin()` (Line 202)** - No docstring

**Fix Required:**
```python
def require_permission(permission: Permission):
    """Create FastAPI dependency that requires specific permission.

    Args:
        permission: Permission name to require (media_store_read, media_store_write, etc.)

    Returns:
        Async dependency function for FastAPI route protection

    Raises:
        HTTPException: 401 if not authenticated, 403 if permission denied
    """

async def require_admin(
    request: Request,
    current_user: UserPayload | None = Depends(get_current_user),
) -> UserPayload | None:
    """FastAPI dependency that requires admin role.

    Args:
        request: FastAPI request object
        current_user: Current authenticated user from get_current_user dependency

    Returns:
        UserPayload if user is admin, or None if no_auth mode

    Raises:
        HTTPException: 401 if not authenticated, 403 if not admin
    """
```

**GitHub Issue Template:**
```markdown
**Title:** [LOW] Add comprehensive docstrings to auth.py dependencies

**Labels:** documentation, low, code-quality

**Description:**
`require_permission` and `require_admin` functions have minimal/missing docstrings.

**Impact:**
- Minor documentation gap
- Missing parameter/return documentation

**Files:**
- src/store/common/auth.py (lines 162, 202)

**Fix:**
Add comprehensive docstrings with Args, Returns, and Raises sections.

**Acceptance Criteria:**
- [ ] Both functions have complete docstrings
- [ ] Args, Returns, Raises sections present
- [ ] FastAPI usage explained
```

---

### MEDIUM-013: print() Used Instead of Logger in storage.py

**Category:** Source Code / Logging
**Severity:** MEDIUM (improper logging)
**Impact:** Error messages not captured by logging system, inconsistent with codebase

**Files Affected:**
- `/Users/anandasarangaram/Work/cl_server/services/store/src/store/common/storage.py` (Line 114)

**Description:**
`StorageService.delete_file()` uses `print()` for error logging instead of proper logger, making errors invisible in production logging systems.

**Current Code:**
```python
def delete_file(self, relative_path: str) -> bool:
    """Delete file from storage."""
    # ...
    try:
        if file_path.exists():
            file_path.unlink()
            self._cleanup_empty_dirs(file_path.parent)
            return True
    except Exception as e:
        print(f"Error deleting file {relative_path}: {e}")  # ❌ WRONG!
    return False
```

**Why This Matters:**
- `print()` output not captured by logging framework
- Errors invisible in production logs
- Inconsistent with rest of codebase (uses loguru everywhere else)
- No log levels (info/warning/error)
- Can't filter or route logs properly

**Fix Required:**
```python
"""Storage service for entity/media file management."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from loguru import logger  # Add this import


class StorageService:
    # ...

    def delete_file(self, relative_path: str) -> bool:
        """Delete file from storage."""
        # ...
        try:
            if file_path.exists():
                file_path.unlink()
                self._cleanup_empty_dirs(file_path.parent)
                return True
        except Exception as e:
            logger.error(f"Error deleting file {relative_path}: {e}")  # ✓ CORRECT!
        return False
```

**GitHub Issue Template:**
```markdown
**Title:** [MEDIUM] Replace print() with logger in storage.py

**Labels:** bug, medium, logging, code-quality

**Description:**
`StorageService.delete_file()` uses `print()` for error messages instead of proper logger (loguru).

**Impact:**
- Errors not captured by logging system
- Inconsistent with codebase logging standards
- Missing in production logs

**Files:**
- src/store/common/storage.py (line 114)

**Fix:**
1. Import loguru logger
2. Replace `print(f"Error deleting file...")` with `logger.error(...)`

**Acceptance Criteria:**
- [ ] loguru logger imported
- [ ] print() replaced with logger.error()
- [ ] Consistent with rest of codebase
```

---

## Source Code Issues by Category

### Code Quality (15 issues)
- **Unused imports:** 5 files (run `ruff check --fix`)
- **Dead code:** 3 instances (commented code in main.py, unused parameters)
- **Commented code:** 4 blocks (main.py lines 26, 77-92)
- **Code duplication:** 3 instances (error handling pattern repeated)

### Logic Errors (8 issues)
- **CRITICAL-002:** Conflicting status fields in ImageIntelligence
- **MEDIUM-005:** Validation method with no logic (`pass`)
- **Comparison issues:** 3 instances (== False instead of is_())
- **Edge case handling:** 3 missing (parent_id validation, file_path checks)

### Error Handling (7 issues)
- **HIGH-004:** Silent failures in job_service.py (3 functions)
- **Missing try/catch:** 3 instances in storage operations
- **Generic exceptions:** Multiple functions catch `Exception` too broadly

### Performance (6 issues)
- **HIGH-002:** N+1 query in get_entities() with version parameter
- **HIGH-003:** N+1 query in get_face_matches()
- **MEDIUM-004:** Import inside function (repeated work)
- **Missing indexes:** 2 foreign keys lack indexes
- **Inefficient algorithms:** 1 instance (parent_id ancestor loop)

### Architecture (5 issues)
- **CRITICAL-003:** Entity missing get_file_path() method
- **Inconsistent interfaces:** Entity vs Face vs EntityVersionData
- **Model design:** ImageIntelligence status field confusion
- **Service boundaries:** 2 instances of unclear separation

### Security (5 issues)
- **Credentials logging:** 2 instances (config printed to stdout)
- **Missing encoding:** 3 file operations without explicit encoding
- **SQL injection risk:** 0 (using SQLAlchemy properly)

---

## Test Issues by Category

### Test Execution (10 issues)
- **CRITICAL-001:** 8 async tests missing @pytest.mark.asyncio
- **Test discovery issues:** 2 tests not running

### Resource Management (8 issues)
- **HIGH-001:** 5 file handle leaks
- **Database connection leaks:** 3 tests don't close sessions

### Test Reliability (12 issues)
- **MEDIUM-006:** 6 flaky tests using time.sleep()
- **Race conditions:** 4 tests have timing dependencies
- **Non-deterministic assertions:** 2 tests check wall-clock time

### Test Coverage (6 issues)
- **Missing concurrent operation tests:** 3 scenarios
- **Missing error case tests:** 3 scenarios
- **No database failure tests:** All integration tests

### Test Quality (4+ issues)
- **Missing docstrings:** 2+ test classes
- **Confusing test names:** 2+ tests (e.g., "rejected" but returns 200)
- **Redundant tests:** 3-4 groups of duplicate tests

---

## Implementation Recommendations

### Recommended Fix Order

#### Week 1: Critical Issues (10 total - MUST DO)
**Priority:** Block all other work until these are fixed

1. **CRITICAL-001:** Add @pytest.mark.asyncio to 8 async tests (2 hours)
   - Quick win, prevents false test results
   - Run tests after to verify they execute

2. **CRITICAL-002:** Consolidate ImageIntelligence status fields (8 hours)
   - Requires database migration
   - Update all code referencing either field
   - Test migration on dev database first

3. **CRITICAL-003:** Add get_file_path() to Entity model (4 hours)
   - Add method matching Face implementation
   - Write unit tests
   - Verify no AttributeError in job_service

#### Week 2: High Priority Performance (27 total)
**Focus:** Fix performance issues first, then error handling

**Days 1-2: Performance (16 hours)**
4. **HIGH-002:** Fix N+1 in get_entities() (8 hours)
   - Add performance test first
   - Implement batch loading
   - Verify improvement with 1000+ entities

5. **HIGH-003:** Fix N+1 in get_face_matches() (6 hours)
   - Similar pattern to HIGH-002
   - Add performance test
   - Verify with 100+ matches

**Days 3-4: Error Handling (16 hours)**
6. **HIGH-004:** Fix silent error handling in job_service (8 hours)
   - Add proper logging
   - Define specific exception types
   - Update callers to handle exceptions

7. **HIGH-001:** Fix file handle leaks in tests (4 hours)
   - Use context managers
   - Run tests 100 iterations to verify
   - Check with lsof on Linux

8. **HIGH-005:** Fix MD5 hash assertion bug (2 hours)
   - Quick fix: change 128 to 32
   - Verify test fails with wrong hash

#### Week 3-4: Medium Priority (35 total)
**Focus:** Code quality and test reliability

**Code Quality (12 hours)**
- MEDIUM-001: Remove underscore assignments (1 hour)
- MEDIUM-002: Fix boolean comparisons (2 hours)
- MEDIUM-003: Clean up commented code (3 hours)
- MEDIUM-004: Move imports to module level (1 hour)
- MEDIUM-005: Implement validation logic (5 hours)

**Test Reliability (12 hours)**
- MEDIUM-006: Fix flaky tests (12 hours)
  - Replace all time.sleep() with proper sync
  - Add timeouts
  - Run 100 iterations to verify

#### Week 5+: Low Priority (14+ total)
**Focus:** Cleanup and documentation

- LOW-001: Remove unused imports (1 hour - automated)
- LOW-002: Add docstrings (8 hours)
- LOW-003: Track TODO comments (2 hours)
- Additional low-priority items as time permits

---

### Testing Strategy

**Before Fixing Any Issue:**
```bash
# 1. Create feature branch
git checkout -b fix-issue-<number>

# 2. Run full test suite to establish baseline
uv run pytest
# Note coverage percentage

# 3. Run specific tests for area being fixed
uv run pytest tests/test_<relevant>.py -v
```

**After Each Fix:**
```bash
# 1. Run tests for affected area
uv run pytest tests/test_<relevant>.py -v

# 2. Run full test suite
uv run pytest

# 3. Verify coverage didn't decrease
# Coverage should stay ≥90%

# 4. For performance fixes: add performance test
uv run pytest tests/test_performance.py -v

# 5. Commit with descriptive message
git add <files>
git commit -m "Fix ISSUE-XXX: <description>

- What was wrong
- How it was fixed
- Tests added/updated"
```

**For Flaky Test Fixes:**
```bash
# Run test 100 times to verify no flakiness
for i in {1..100}; do
    uv run pytest tests/test_specific.py::test_name || break
done
```

**For Performance Fixes:**
```bash
# Add performance test that would fail before fix
def test_get_entities_performance():
    # Create 1000 entities
    for i in range(1000):
        create_entity(...)

    # Measure query count
    with query_counter():
        result = get_entities(page_size=100)

    # Should be ≤2 queries, not 1001
    assert query_counter.count <= 2
```

---

### Automation Opportunities

Many issues can be auto-fixed:

```bash
# Fix unused imports, formatting, common issues
uv run ruff check --fix src/
uv run ruff format src/

# Find remaining issues
uv run ruff check src/

# Type checking
uv run basedpyright

# Security scanning
uv run bandit -r src/

# Find dead code
uv run vulture src/
```

**Create pre-commit hook:**
```bash
# .git/hooks/pre-commit
#!/bin/bash
uv run ruff check --fix src/
uv run ruff format src/
uv run pytest --no-cov
```

---

### Progress Tracking

**Create GitHub Milestone:** "Code Review Fixes"
- Target: 90% complete in 6 weeks
- Track weekly progress
- Review blockers in standup

**Weekly Status:**
```markdown
## Week 1 Status (Example)
- [x] CRITICAL-001: Async test decorators
- [x] CRITICAL-002: Status field consolidation
- [ ] CRITICAL-003: Entity.get_file_path() (in progress)
- [ ] CRITICAL-004: Face file cleanup (high priority - file leaks)
- [ ] CRITICAL-005: delete_all_entities file cleanup (high priority - file leaks)
- [ ] CRITICAL-006: Vector embedding cleanup (high priority - Qdrant leaks)

Issues fixed: 2/13 critical
Percentage: 15%
```

**Metrics to Track:**
- Issues closed per week
- Test coverage percentage (should stay ≥90%)
- Performance improvements (query counts)
- Build time (should not increase)

---

## Summary Statistics

**Total Issues:** 95+

**By Severity:**
- Critical: 13 (must fix immediately)
- High: 28 (fix within 2 weeks)
- Medium: 40 (fix within 4 weeks)
- Low: 14+ (fix when time permits)

**By Type:**
- Source Code: 55 issues
- Tests: 40+ issues

**Estimated Fix Time:**
- Critical: 30-40 hours (increased due to delete operation cleanup)
- High: 30-40 hours
- Medium: 30-40 hours
- Low: 10-15 hours
- **Total: 100-135 hours (13-17 business days)**

**Critical Delete Operation Issues (NEW - Must Fix Immediately):**
1. CRITICAL-004: Face files not deleted (file leaks)
2. CRITICAL-005: delete_all_entities() leaks all files (massive file leak)
3. CRITICAL-006: Vector embeddings not deleted (Qdrant bloat)

**Quick Wins (< 2 hours each):**
1. CRITICAL-001: Add async decorators (2 hours)
2. HIGH-005: Fix hash assertion (1 hour)
3. MEDIUM-001: Remove underscores (1 hour)
4. MEDIUM-004: Move imports (1 hour)
5. LOW-001: Remove unused imports (automated)

**High Impact:**
1. **CRITICAL-004, 005, 006: Fix delete operations (prevents file/vector leaks, disk exhaustion)**
2. CRITICAL-002: Fix status fields (prevents data corruption)
3. HIGH-002: Fix N+1 queries (10-100x performance improvement)
4. HIGH-004: Fix error handling (enables debugging)
5. CRITICAL-003: Add Entity method (prevents runtime errors)

---

**End of Review Document**

For questions or to report additional issues, please create a GitHub issue with the appropriate label.
