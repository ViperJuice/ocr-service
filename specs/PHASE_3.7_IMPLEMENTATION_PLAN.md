# Phase 3.7: Performance & Architecture Optimization
## Architecture-First Implementation Plan with Code-Level Interface Boundaries

**Generated:** 2025-11-16
**Phase Scope:** Phase 3.7 (A, B, C) from [MASTER_ROADMAP.md](MASTER_ROADMAP.md)
**Status:** Planning
**Estimated Total Duration:** 22-30 hours (3-4 days)

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Architectural Baseline & Component Catalog](#architectural-baseline--component-catalog)
3. [Code-Level Interface Contracts](#code-level-interface-contracts)
4. [Exhaustive Change List](#exhaustive-change-list)
5. [Swim Lane Derivation](#swim-lane-derivation)
6. [Implementation Plan](#implementation-plan)
7. [Testing Strategy](#testing-strategy)
8. [Rollback Plan](#rollback-plan)

---

## Executive Summary

Phase 3.7 addresses critical performance bottlenecks before Phase 4's database-only migration:

**Performance Goals:**
- 10x reduction in disk I/O operations
- 10x reduction in database transactions
- 2x batch processing throughput
- 3-5x per-document processing speedup
- **Overall: 6-10x faster end-to-end processing**

**Architecture Strategy:**
Phase 3.7 is divided into three independent sub-phases that can be implemented in parallel:

- **Phase 3.7A (I/O Optimization):** Buffering and batching for disk/DB writes - Highest ROI, lowest risk
- **Phase 3.7B (Batch Parallelization):** Concurrent document processing in batch jobs
- **Phase 3.7C (Page-Level Optimization):** Mini-batch inference or parallel page processing

**Why This Matters:**
Phase 4 will remove in-memory state and rely exclusively on database operations. Current performance bottlenecks will be **amplified** when reading from database instead of memory. Fixing these issues now prevents performance regression.

---

## Architectural Baseline & Component Catalog

### Current Architecture (Pre-Phase 3.7)

```
┌─────────────────────────────────────────────────────────┐
│  Pipeline Processing (StagedPipeline)                   │
│  - Sequential page processing (1 page at a time)        │
│  - Write output after EVERY page (100 writes/100 pages) │
│  - DB insert after EVERY page (100 INSERTs/100 pages)   │
│  - Checkpoint after EVERY page (100 checkpoints)        │
│  - No cache cleanup (orphaned directories accumulate)   │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  Batch Processing (BatchManager)                        │
│  - Sequential document processing (1 doc at a time)     │
│  - max_concurrent_jobs=2 UNUSED for batches             │
│  - 100 docs × 2 min = 200 minutes (no parallelism)      │
└─────────────────────────────────────────────────────────┘
```

### Target Architecture (Post-Phase 3.7)

```
┌─────────────────────────────────────────────────────────┐
│  Pipeline Processing (StagedPipeline)                   │
│  - Buffered output writes (10 pages/write)              │
│  - Bulk DB inserts (10 pages/batch)                     │
│  - Checkpoint every 5 pages OR 30 seconds               │
│  - Automatic cache cleanup (finally block + hourly)     │
│  - OPTIONAL: Mini-batch inference (4-8 pages/request)   │
│  - OPTIONAL: Parallel page processing (ThreadPool)      │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  Batch Processing (BatchManager)                        │
│  - Concurrent document processing (2 docs in parallel)  │
│  - asyncio.gather() + Semaphore(max_concurrent_jobs)    │
│  - 100 docs / 2 workers × 2 min = 100 minutes (2x)      │
│  - Thread-safe progress aggregation                     │
└─────────────────────────────────────────────────────────┘
```

---

## A. Architectural Baseline & Component Catalog

### Files Modified/Added

#### Phase 3.7A: I/O Optimization

| File | Change Type | Description |
|------|-------------|-------------|
| `src/preprocessing/staged_pipeline.py` | **MODIFIED** | Add output buffering (10 pages/write) |
| `src/database/repositories/job_repository.py` | **MODIFIED** | Add `bulk_create_page_results()` method |
| `src/preprocessing/checkpoint_manager.py` | **MODIFIED** | Checkpoint every 5 pages OR 30 seconds |
| `src/api/main.py` | **MODIFIED** | Add hourly cache cleanup background task |
| `src/api/services/cache_cleanup.py` | **ADDED** | Cache cleanup service (new file) |

#### Phase 3.7B: Batch Parallelization

| File | Change Type | Description |
|------|-------------|-------------|
| `src/api/services/batch_manager.py` | **MODIFIED** | Replace sequential loop with `asyncio.gather()` + `Semaphore` |
| `src/api/batch_routes.py` | **MODIFIED** | Aggregate concurrent progress updates |
| `src/api/services/job_manager.py` | **AUDIT** | Verify thread safety (add locks if needed) |
| `src/api/services/result_emitter.py` | **AUDIT** | Verify thread safety (add locks if needed) |

#### Phase 3.7C: Page-Level Optimization (Option A: Mini-Batch)

| File | Change Type | Description |
|------|-------------|-------------|
| `src/models/model_manager.py` | **MODIFIED** | Add `infer_batch()` method for batch inference |
| `src/preprocessing/staged_pipeline.py` | **MODIFIED** | Replace page loop with batch loop (BATCH_SIZE=4-8) |
| `src/api/services/result_emitter.py` | **MODIFIED** | Emit progress per batch (not per page) |
| `baml_src/ocr.baml` | **OPTIONAL** | Add batch inference function (if BAML used) |

#### Phase 3.7C: Page-Level Optimization (Option B: Parallel Pages)

| File | Change Type | Description |
|------|-------------|-------------|
| `src/models/model_manager.py` | **MODIFIED** | Add connection pooling or request locks |
| `src/preprocessing/staged_pipeline.py` | **MODIFIED** | Replace page loop with ThreadPoolExecutor |
| `src/api/services/result_emitter.py` | **MODIFIED** | Handle out-of-order page completion |

---

### Classes Modified/Added

#### Phase 3.7A: I/O Optimization

**New Class:**
```python
# src/api/services/cache_cleanup.py
class CacheCleanupService:
    """Service for cleaning up expired cache directories and uploads."""

    def __init__(self, upload_dir: Path, cache_dir: Path, max_age_hours: int = 24)
    async def cleanup_expired_files(self) -> Dict[str, int]
    async def cleanup_job_cache(self, job_id: str) -> None
```

**Modified Class:**
```python
# src/database/repositories/job_repository.py
class JobRepository(BaseRepository):
    # EXISTING METHODS...

    # NEW METHOD (Phase 3.7A)
    async def bulk_create_page_results(
        self,
        job_id: UUID,
        page_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]
```

**Modified Class:**
```python
# src/preprocessing/checkpoint_manager.py
class CheckpointManager:
    # EXISTING METHODS...

    # MODIFIED (Phase 3.7A)
    def __init__(self, output_path: Path, pdf_path: Path, processing_params: Dict[str, Any]):
        # ... existing fields ...
        self._last_checkpoint_time: float = time.time()  # NEW
        self._checkpoint_interval_pages: int = 5  # NEW (default 5)
        self._checkpoint_interval_seconds: float = 30.0  # NEW (default 30s)

    def should_save_checkpoint(self, pages_since_last: int) -> bool:  # NEW METHOD
```

#### Phase 3.7B: Batch Parallelization

**Modified Class:**
```python
# src/api/services/batch_manager.py
class BatchManager:
    # MODIFIED METHOD (Phase 3.7B)
    async def _process_batch_concurrent(  # NEW NAME (was _process_batch_async)
        self,
        batch: BatchJob,
        file_manager,
        job_manager,
        prompt_manager,
        model_manager,
        progress_emitter
    ) -> None:
        # Uses asyncio.gather() + Semaphore for concurrency
```

#### Phase 3.7C: Page-Level Optimization (Option A)

**Modified Class:**
```python
# src/models/model_manager.py
class ModelManager:
    # NEW METHOD (Phase 3.7C - Option A)
    async def infer_batch_with_container(
        self,
        model_name: str,
        images: List[Image.Image],
        prompt: Optional[str] = None,
        messages: Optional[list] = None,
        prompt_type: str = "ocr",
        auto_unload: bool = True,
        **kwargs
    ) -> List[OCRResult]:
        """Batch inference: send multiple images in single request."""
```

#### Phase 3.7C: Page-Level Optimization (Option B)

**Modified Class:**
```python
# src/models/model_manager.py
class ModelManager:
    def __init__(self, model_configs: Dict[str, Dict]):
        # ... existing fields ...
        self._request_lock: asyncio.Lock = asyncio.Lock()  # NEW (for thread safety)
```

---

### Functions/Methods Modified

#### Phase 3.7A: I/O Optimization

**1. StagedPipeline: Output Buffering**
```python
# src/preprocessing/staged_pipeline.py
class StagedPipeline:
    OUTPUT_BUFFER_SIZE = 10  # NEW CONSTANT

    async def process_pdf(self, ...):
        # MODIFIED: Buffer output writes
        output_buffer: List[str] = []  # NEW

        for idx, page in enumerate(pages):
            # ... process page ...
            output_buffer.append(merged_text)

            # Write buffer every OUTPUT_BUFFER_SIZE pages
            if len(output_buffer) >= self.OUTPUT_BUFFER_SIZE:
                await self._flush_output_buffer(output_buffer)  # NEW METHOD
                output_buffer.clear()

        # Flush remaining pages
        if output_buffer:
            await self._flush_output_buffer(output_buffer)

    async def _flush_output_buffer(self, buffer: List[str]) -> None:  # NEW METHOD
        """Write buffered pages to output file."""
```

**2. JobRepository: Bulk Page Results**
```python
# src/database/repositories/job_repository.py
class JobRepository(BaseRepository):
    async def bulk_create_page_results(
        self,
        job_id: UUID,
        page_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Bulk insert page results (10x faster than individual inserts).

        Args:
            job_id: Job UUID
            page_results: List of page result dicts with keys:
                - page_num: int
                - ocr_text: Optional[str]
                - ocr_processing_time: Optional[float]
                - merge_text: Optional[str]
                - merge_processing_time: Optional[float]

        Returns:
            List of created page result records
        """
```

**3. CheckpointManager: Adaptive Checkpointing**
```python
# src/preprocessing/checkpoint_manager.py
class CheckpointManager:
    def should_save_checkpoint(self, pages_since_last: int) -> bool:
        """
        Determine if checkpoint should be saved based on:
        - Pages processed since last checkpoint (default: 5)
        - Time elapsed since last checkpoint (default: 30s)

        Returns True if EITHER condition is met.
        """
        time_elapsed = time.time() - self._last_checkpoint_time
        return (
            pages_since_last >= self._checkpoint_interval_pages
            or time_elapsed >= self._checkpoint_interval_seconds
        )

    def save(self, checkpoint_data: Dict[str, Any]) -> None:
        """Save checkpoint and update last checkpoint time."""
        # ... existing save logic ...
        self._last_checkpoint_time = time.time()  # NEW
```

**4. CacheCleanupService: Automated Cleanup**
```python
# src/api/services/cache_cleanup.py (NEW FILE)
class CacheCleanupService:
    async def cleanup_expired_files(self) -> Dict[str, int]:
        """
        Clean up expired uploads and cache directories.

        Returns:
            Dict with counts: {"uploads_deleted": N, "caches_deleted": M}
        """

    async def cleanup_job_cache(self, job_id: str) -> None:
        """Clean up cache for specific job (called in finally block)."""
```

**5. FastAPI Main: Background Cleanup Task**
```python
# src/api/main.py
@app.on_event("startup")
async def startup_event():
    # ... existing startup code ...

    # NEW: Schedule hourly cache cleanup
    from src.api.services.cache_cleanup import CacheCleanupService
    cache_cleanup = CacheCleanupService(
        upload_dir=settings.UPLOAD_DIR,
        cache_dir=settings.CACHE_DIR,
        max_age_hours=24
    )

    asyncio.create_task(run_periodic_cleanup(cache_cleanup))  # NEW

async def run_periodic_cleanup(service: CacheCleanupService):  # NEW FUNCTION
    """Run cleanup every hour."""
    while True:
        await asyncio.sleep(3600)  # 1 hour
        try:
            stats = await service.cleanup_expired_files()
            logger.info(f"Cache cleanup: {stats}")
        except Exception as e:
            logger.error(f"Cache cleanup failed: {e}")
```

#### Phase 3.7B: Batch Parallelization

**1. BatchManager: Concurrent Processing**
```python
# src/api/services/batch_manager.py
class BatchManager:
    async def _process_batch_concurrent(
        self,
        batch: BatchJob,
        file_manager,
        job_manager,
        prompt_manager,
        model_manager,
        progress_emitter
    ) -> None:
        """
        Process batch documents concurrently (up to max_concurrent_jobs).

        Uses asyncio.gather() with Semaphore to limit concurrency.
        """
        from asyncio import Semaphore, gather

        max_concurrent = job_manager.max_concurrent_jobs  # e.g., 2
        semaphore = Semaphore(max_concurrent)

        async def process_one_doc(file_id: str, idx: int):
            async with semaphore:
                # Check cancellation
                if batch.cancel_requested:
                    return None

                # Process document (existing logic)
                job_id = await job_manager.create_job(...)
                await job_manager.process_job(job_id, ...)

                # Update batch progress
                async with self.batch_lock:
                    batch.completed_files += 1
                    progress = (batch.completed_files / len(batch.file_ids)) * 100
                    progress_emitter.emit_batch_progress(batch.batch_job_id, progress)

                return job_id

        # Process all documents concurrently (limited by semaphore)
        tasks = [process_one_doc(fid, i) for i, fid in enumerate(batch.file_ids)]
        results = await gather(*tasks, return_exceptions=True)

        # Handle results and errors
        # ...
```

**2. Batch Routes: Aggregate Progress**
```python
# src/api/batch_routes.py
async def stream_batch_progress(batch_id: str):
    """
    Stream batch progress (handles concurrent job updates).

    Aggregates progress from multiple concurrent jobs.
    """
```

#### Phase 3.7C: Page-Level Optimization (Option A: Mini-Batch)

**1. ModelManager: Batch Inference**
```python
# src/models/model_manager.py
class ModelManager:
    async def infer_batch_with_container(
        self,
        model_name: str,
        images: List[Image.Image],
        prompt: Optional[str] = None,
        messages: Optional[list] = None,
        prompt_type: str = "ocr",
        auto_unload: bool = True,
        **kwargs
    ) -> List[OCRResult]:
        """
        Batch inference: send multiple images in single request.

        Args:
            images: List of PIL Images (4-8 recommended)
            ... (same as infer_with_container)

        Returns:
            List of OCRResult (one per image, same order)

        Raises:
            RuntimeError: If container doesn't support batch inference
        """
        if self.http_client_manager is None:
            raise RuntimeError("Container mode not initialized")

        # Convert all images to base64
        images_b64 = [self._image_to_base64(img) for img in images]

        # Build batch request
        request_data = {
            "images_base64": images_b64,  # NEW: multiple images
            "prompt": prompt,
            # ... other config ...
        }

        # Call container
        response = await client.post(f"{url}/infer_batch", json=request_data)
        results = response.json()["results"]  # List of OCR results

        # Convert to OCRResult objects
        return [OCRResult(...) for r in results]
```

**2. StagedPipeline: Batch Page Processing**
```python
# src/preprocessing/staged_pipeline.py
class StagedPipeline:
    PAGE_BATCH_SIZE = 4  # NEW CONSTANT (configurable: 4, 8, 16)

    async def process_pdf(self, ...):
        # ... existing setup ...

        # MODIFIED: Process pages in batches
        for batch_start in range(0, total_pages, self.PAGE_BATCH_SIZE):
            batch_end = min(batch_start + self.PAGE_BATCH_SIZE, total_pages)
            batch_pages = pages[batch_start:batch_end]

            # Extract images for batch
            batch_images = [page.extract_image() for page in batch_pages]

            # Batch OCR inference
            ocr_results = await self.model_manager.infer_batch_with_container(
                model_name="deepseek-ocr",
                images=batch_images,
                prompt=ocr_prompt
            )

            # Process each result
            for idx, (page, ocr_result) in enumerate(zip(batch_pages, ocr_results)):
                # ... merge, emit progress, buffer output ...
                pass

            # Emit batch progress
            if self.result_emitter:
                progress = ((batch_end) / total_pages) * 100
                self.result_emitter.emit_batch_progress(self.job_id, progress)
```

#### Phase 3.7C: Page-Level Optimization (Option B: Parallel Pages)

**1. ModelManager: Thread-Safe Requests**
```python
# src/models/model_manager.py
class ModelManager:
    def __init__(self, model_configs: Dict[str, Dict]):
        # ... existing fields ...
        self._request_lock: asyncio.Lock = asyncio.Lock()  # NEW

    async def infer_with_container(self, ...):
        # MODIFIED: Add lock for thread safety
        async with self._request_lock:
            # ... existing inference logic ...
            pass
```

**2. StagedPipeline: Parallel Page Processing**
```python
# src/preprocessing/staged_pipeline.py
class StagedPipeline:
    MAX_PAGE_WORKERS = 4  # NEW CONSTANT (configurable: 2, 4, 8)

    async def process_pdf(self, ...):
        from concurrent.futures import ThreadPoolExecutor
        from asyncio import gather

        # ... existing setup ...

        async def process_one_page(page_num: int, page_data):
            # Extract image
            image = page_data.extract_image()

            # OCR inference
            ocr_result = await self.model_manager.infer_with_container(...)

            # Merge inference
            merge_result = await self.model_manager.infer_with_container(...)

            # Return result
            return (page_num, merge_result.text, ocr_result.processing_time, merge_result.processing_time)

        # MODIFIED: Process pages in parallel
        tasks = [process_one_page(i, page) for i, page in enumerate(pages)]
        results = await gather(*tasks)

        # Sort results by page number (may complete out of order)
        results.sort(key=lambda x: x[0])

        # Write results
        for page_num, text, ocr_time, merge_time in results:
            # ... buffer output, emit progress ...
            pass
```

---

### Data Structures Modified/Added

#### Phase 3.7A: I/O Optimization

**Bulk Page Results Input Schema:**
```python
# src/database/repositories/job_repository.py
PageResultInput = TypedDict('PageResultInput', {
    'page_num': int,                          # Required: 1-indexed page number
    'ocr_text': NotRequired[str],             # Optional: OCR extracted text
    'ocr_processing_time': NotRequired[float], # Optional: OCR time in seconds
    'merge_text': NotRequired[str],           # Optional: Merged text
    'merge_processing_time': NotRequired[float] # Optional: Merge time in seconds
})

# Used in:
async def bulk_create_page_results(
    job_id: UUID,
    page_results: List[PageResultInput]
) -> List[Dict[str, Any]]
```

**Cache Cleanup Stats Schema:**
```python
# src/api/services/cache_cleanup.py
CleanupStats = TypedDict('CleanupStats', {
    'uploads_deleted': int,      # Number of expired uploads deleted
    'caches_deleted': int,        # Number of cache directories deleted
    'bytes_freed': int,           # Total disk space freed (bytes)
    'duration_seconds': float     # Cleanup duration
})
```

#### Phase 3.7B: Batch Parallelization

**Batch Progress Event Schema:**
```python
# src/api/services/progress_emitter.py
BatchProgressEvent = TypedDict('BatchProgressEvent', {
    'batch_id': str,              # Batch job ID
    'total_files': int,           # Total documents in batch
    'completed_files': int,       # Documents completed
    'active_files': int,          # Documents currently processing (NEW)
    'failed_files': int,          # Documents that failed
    'progress_percent': float,    # Overall progress (0-100)
    'timestamp': str              # ISO 8601 timestamp
})
```

#### Phase 3.7C: Page-Level Optimization (Option A)

**Batch Inference Request Schema:**
```python
# Container API (external interface)
BatchInferenceRequest = TypedDict('BatchInferenceRequest', {
    'images_base64': List[str],   # Multiple base64-encoded images
    'prompt': str,                # Shared prompt for all images
    'base_size': int,             # DeepSeek config
    'image_size': int,            # DeepSeek config
    'crop_mode': bool,            # DeepSeek config
    'auto_unload': bool           # Whether to unload model after
})

BatchInferenceResponse = TypedDict('BatchInferenceResponse', {
    'success': bool,
    'results': List[Dict[str, Any]],  # List of OCR results (same order as input)
    'processing_time': float,         # Total time for batch
    'model_name': str
})
```

---

## B. Code-Level Interface Contracts

### Interface Freeze Gates

**IF-0-3.7A:** I/O Optimization Interfaces
**IF-0-3.7B:** Batch Parallelization Interfaces
**IF-0-3.7C:** Page-Level Optimization Interfaces

All interfaces below MUST be frozen before implementation work begins in dependent swim lanes.

---

### Interface Group 1: I/O Optimization (Phase 3.7A)

#### Interface 1.1: Bulk Database Writes

**Owner:** Swim Lane A1 (Database Layer)
**Consumers:** Swim Lane A2 (Pipeline Integration)

```python
# src/database/repositories/job_repository.py
class JobRepository(BaseRepository):
    async def bulk_create_page_results(
        self,
        job_id: UUID,
        page_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Bulk insert page results (10x faster than individual inserts).

        Args:
            job_id: Job UUID (must exist in jobs table)
            page_results: List of dicts with keys:
                - page_num: int (required, 1-indexed)
                - ocr_text: str (optional)
                - ocr_processing_time: float (optional)
                - merge_text: str (optional)
                - merge_processing_time: float (optional)

        Returns:
            List of created page_results records (full schema with IDs, timestamps)

        Raises:
            ValueError: If job_id doesn't exist or page_results is empty
            DatabaseError: If bulk insert fails (transaction rolled back)

        Performance:
            - 100 pages: ~100ms (vs 1000ms for individual inserts)
            - Atomic: All pages inserted or none (transaction)

        Example:
            page_results = [
                {"page_num": 1, "ocr_text": "Page 1...", "ocr_processing_time": 1.2},
                {"page_num": 2, "ocr_text": "Page 2...", "ocr_processing_time": 1.3},
                # ... 8 more pages ...
            ]
            results = await job_repo.bulk_create_page_results(job_id, page_results)
        """
```

**Contract Invariants:**
- Input list must contain 1-1000 page results (validated)
- All `page_num` values must be unique within the list
- `job_id` must reference existing job (foreign key constraint)
- Returns results in same order as input
- Transaction guarantees: all-or-nothing insert
- Idempotent: If page_num already exists for job, UPDATE instead of INSERT

---

#### Interface 1.2: Adaptive Checkpointing

**Owner:** Swim Lane A1 (Database Layer)
**Consumers:** Swim Lane A2 (Pipeline Integration)

```python
# src/preprocessing/checkpoint_manager.py
class CheckpointManager:
    def should_save_checkpoint(self, pages_since_last: int) -> bool:
        """
        Determine if checkpoint should be saved.

        Checkpoint triggers (OR condition):
        - Pages processed >= checkpoint_interval_pages (default: 5)
        - Time elapsed >= checkpoint_interval_seconds (default: 30.0)

        Args:
            pages_since_last: Number of pages processed since last checkpoint

        Returns:
            True if checkpoint should be saved, False otherwise

        Side Effects:
            None (read-only, stateless check)

        Example:
            if checkpoint_mgr.should_save_checkpoint(pages_processed):
                checkpoint_mgr.save(checkpoint_data)
        """

    def save(self, checkpoint_data: Dict[str, Any]) -> None:
        """
        Save checkpoint to disk and update internal timestamp.

        Args:
            checkpoint_data: Checkpoint state dict (schema unchanged from current)

        Side Effects:
            - Writes checkpoint file to disk (atomic write)
            - Updates self._last_checkpoint_time = time.time()

        Raises:
            IOError: If checkpoint file cannot be written
        """
```

**Contract Invariants:**
- `should_save_checkpoint()` must be called BEFORE `save()`
- After `save()`, `_last_checkpoint_time` reset to current time
- Checkpoint file written atomically (temp file + rename)
- Checkpoint schema unchanged from current implementation

---

#### Interface 1.3: Cache Cleanup Service

**Owner:** Swim Lane A3 (Cleanup Service)
**Consumers:** Main application startup, Pipeline finally blocks

```python
# src/api/services/cache_cleanup.py
class CacheCleanupService:
    def __init__(
        self,
        upload_dir: Path,
        cache_dir: Path,
        max_age_hours: int = 24
    ):
        """
        Initialize cache cleanup service.

        Args:
            upload_dir: Path to upload directory
            cache_dir: Path to cache directory
            max_age_hours: Maximum age for files (default: 24 hours)
        """

    async def cleanup_expired_files(self) -> Dict[str, int]:
        """
        Clean up expired uploads and cache directories.

        Criteria for deletion:
        - File/directory age > max_age_hours
        - Parent directory is upload_dir or cache_dir
        - NOT associated with active jobs (checked via job_manager)

        Returns:
            Stats dict: {"uploads_deleted": N, "caches_deleted": M, "bytes_freed": B}

        Side Effects:
            - Deletes expired files and directories from disk
            - Logs deletions at INFO level

        Error Handling:
            - Continues on individual file errors (logs warning)
            - Never raises exceptions (safe for background tasks)

        Performance:
            - Scans up to 10,000 files in ~100-500ms
            - Deletes up to 1000 files in ~1-5 seconds
        """

    async def cleanup_job_cache(self, job_id: str) -> None:
        """
        Clean up cache for specific job (called in finally block).

        Args:
            job_id: Job ID to clean up

        Side Effects:
            - Deletes cache directory for job (if exists)
            - Logs cleanup at DEBUG level

        Error Handling:
            - Never raises exceptions (safe for finally blocks)
            - Logs errors at WARNING level
        """
```

**Contract Invariants:**
- `cleanup_expired_files()` never raises exceptions (safe for background tasks)
- `cleanup_job_cache()` never raises exceptions (safe for finally blocks)
- Deletes only files older than `max_age_hours`
- Active jobs are NEVER deleted (cross-referenced with job_manager)

---

### Interface Group 2: Batch Parallelization (Phase 3.7B)

#### Interface 2.1: Concurrent Batch Processing

**Owner:** Swim Lane B1 (Batch Manager)
**Consumers:** Batch Routes, Job Manager

```python
# src/api/services/batch_manager.py
class BatchManager:
    async def _process_batch_concurrent(
        self,
        batch: BatchJob,
        file_manager: FileManager,
        job_manager: JobManager,
        prompt_manager: PromptManager,
        model_manager: ModelManager,
        progress_emitter: ProgressEmitter
    ) -> None:
        """
        Process batch documents concurrently (up to max_concurrent_jobs).

        Concurrency:
        - Max concurrent jobs: job_manager.max_concurrent_jobs (default: 2)
        - Uses asyncio.gather() + Semaphore
        - Jobs processed in FIFO order (within concurrency limit)

        Progress Tracking:
        - Emits progress after each document completes
        - Progress = (completed_files / total_files) * 100
        - Thread-safe: Uses batch_lock for progress updates

        Error Handling:
        - Individual job failures don't stop batch
        - Failed jobs logged, batch continues
        - Batch status = FAILED if ALL jobs fail
        - Batch status = PARTIAL_SUCCESS if SOME jobs fail
        - Batch status = COMPLETED if all jobs succeed

        Cancellation:
        - Checks batch.cancel_requested before each job
        - Ongoing jobs finish, remaining jobs skipped
        - Batch status = CANCELLED

        Args:
            batch: BatchJob object (mutable, updated in-place)
            ... (managers passed as dependencies)

        Side Effects:
            - Updates batch.status, batch.completed_files, batch.completed_at
            - Creates individual jobs in job_manager
            - Emits progress events via progress_emitter

        Performance:
            - 100 docs @ 2 min each, max_concurrent=2: ~100 minutes (vs 200 sequential)
        """
```

**Contract Invariants:**
- Concurrency limited to `job_manager.max_concurrent_jobs`
- Progress emitted after each document completion (not per page)
- Failed jobs don't block other jobs
- Batch progress is thread-safe (uses `batch_lock`)
- Cancellation is checked before starting each job (not mid-job)

---

#### Interface 2.2: Batch Progress Aggregation

**Owner:** Swim Lane B2 (Batch Routes)
**Consumers:** Frontend (SSE/Realtime subscribers)

```python
# src/api/batch_routes.py
async def stream_batch_progress(batch_id: str) -> AsyncIterator[str]:
    """
    Stream batch progress events (SSE).

    Event Schema:
        {
            "batch_id": str,
            "total_files": int,
            "completed_files": int,
            "active_files": int,       # NEW: currently processing
            "failed_files": int,
            "progress_percent": float,
            "timestamp": str
        }

    Progress Calculation:
        progress_percent = (completed_files / total_files) * 100
        active_files = jobs in "processing" state

    Concurrency Handling:
        - Aggregates progress from multiple concurrent jobs
        - Thread-safe: Uses batch_manager.batch_lock

    Error Handling:
        - Invalid batch_id: HTTP 404
        - Batch cancelled: Emits final event with status="cancelled"

    Yields:
        SSE events (Server-Sent Events format)
    """
```

**Contract Invariants:**
- `active_files` accurately reflects concurrent jobs in progress
- `progress_percent` monotonically increases (0 → 100)
- Final event emitted when batch completes (status in: completed, failed, cancelled)

---

### Interface Group 3: Page-Level Optimization (Phase 3.7C - Option A)

#### Interface 3.1: Batch Inference (Container API)

**Owner:** External (GPU Containers)
**Consumers:** Swim Lane C1 (Model Manager)

```python
# Container API (external HTTP endpoint)
POST /infer_batch
Content-Type: application/json

Request:
{
    "images_base64": ["<base64_1>", "<base64_2>", ..., "<base64_N>"],  # 1-16 images
    "prompt": str,
    "base_size": int,      # DeepSeek config
    "image_size": int,     # DeepSeek config
    "crop_mode": bool,     # DeepSeek config
    "auto_unload": bool
}

Response (200 OK):
{
    "success": true,
    "results": [
        {
            "text": str,
            "model_name": str,
            "processing_time": float
        },
        // ... N results (same order as input images)
    ],
    "total_processing_time": float,
    "model_name": str
}

Response (400 Bad Request):
{
    "success": false,
    "error": "Invalid request: images_base64 must contain 1-16 images"
}

Response (500 Internal Server Error):
{
    "success": false,
    "error": "Inference failed: <error_message>"
}
```

**Contract Invariants:**
- Accepts 1-16 images per request (validated)
- Returns results in SAME ORDER as input images
- `total_processing_time` ≈ sum of individual processing times
- Atomic: Either all images processed or request fails
- Thread-safe: Container handles concurrent requests (up to 4 concurrent)

**Dependencies:**
- **BLOCKER:** Container must implement `/infer_batch` endpoint before Swim Lane C1 work begins
- Swim Lane C1 cannot start until container API is ready (IF-0-3.7C gate)

---

#### Interface 3.2: Batch Inference (Python Client)

**Owner:** Swim Lane C1 (Model Manager)
**Consumers:** Swim Lane C2 (Pipeline Integration)

```python
# src/models/model_manager.py
class ModelManager:
    async def infer_batch_with_container(
        self,
        model_name: str,
        images: List[Image.Image],
        prompt: Optional[str] = None,
        messages: Optional[list] = None,
        prompt_type: str = "ocr",
        auto_unload: bool = True,
        **kwargs
    ) -> List[OCRResult]:
        """
        Batch inference: send multiple images in single request.

        Args:
            model_name: "deepseek-ocr" or "qwen3-vl-*"
            images: List of PIL Images (1-16 recommended, 4-8 optimal)
            prompt: Shared prompt for all images
            ... (same as infer_with_container)

        Returns:
            List of OCRResult (one per image, same order as input)

        Raises:
            RuntimeError: If container not initialized or doesn't support batch
            ValueError: If images list is empty or exceeds max batch size

        Performance:
            - 8 images @ 1.5s each sequential = 12s
            - 8 images @ 2.5s batch = 2.5s (4.8x speedup)

        Example:
            images = [page1_img, page2_img, page3_img, page4_img]
            results = await model_manager.infer_batch_with_container(
                model_name="deepseek-ocr",
                images=images,
                prompt="Free OCR."
            )
            # results[0] = OCRResult for page1_img, etc.
        """
```

**Contract Invariants:**
- Input images list: 1-16 images (validated)
- Output list: same length as input, same order
- All images processed with same prompt
- Raises exception if container doesn't support batch inference

---

### Interface Group 3: Page-Level Optimization (Phase 3.7C - Option B)

#### Interface 3.3: Thread-Safe Container Requests

**Owner:** Swim Lane C1 (Model Manager)
**Consumers:** Swim Lane C2 (Pipeline Integration - Parallel)

```python
# src/models/model_manager.py
class ModelManager:
    async def infer_with_container(
        self,
        model_name: str,
        image: Image.Image,
        prompt: Optional[str] = None,
        messages: Optional[list] = None,
        prompt_type: str = "ocr",
        auto_unload: bool = True,
        **kwargs
    ) -> OCRResult:
        """
        Thread-safe inference (supports concurrent requests).

        MODIFIED FOR PHASE 3.7C-B:
        - Uses internal asyncio.Lock to serialize requests
        - Safe for concurrent calls from multiple tasks

        Concurrency:
        - Max concurrent requests: Limited by lock (serialized)
        - Alternative: Connection pool (4-8 concurrent connections)

        Args, Returns, Raises:
            (Same as current implementation)

        Performance:
            - 4 parallel tasks × 25 pages each = ~25s per task
            - vs 100 pages sequential = ~100s
        """
```

**Contract Invariants:**
- Thread-safe: Can be called concurrently from multiple async tasks
- Request serialization: Internal lock ensures no race conditions
- No change to existing method signature (backward compatible)

---

## C. Exhaustive Change List

### Phase 3.7A: I/O Optimization

| File | Component | Change Type | Description |
|------|-----------|-------------|-------------|
| `src/database/repositories/job_repository.py` | `JobRepository.bulk_create_page_results()` | **ADD METHOD** | Bulk insert page results (10 pages/batch) |
| `src/preprocessing/staged_pipeline.py` | `StagedPipeline.OUTPUT_BUFFER_SIZE` | **ADD CONSTANT** | Buffer size = 10 pages |
| `src/preprocessing/staged_pipeline.py` | `StagedPipeline.process_pdf()` | **MODIFY** | Add output buffering logic |
| `src/preprocessing/staged_pipeline.py` | `StagedPipeline._flush_output_buffer()` | **ADD METHOD** | Flush buffered pages to disk |
| `src/preprocessing/staged_pipeline.py` | `StagedPipeline.process_pdf()` | **MODIFY** | Call `bulk_create_page_results()` instead of individual inserts |
| `src/preprocessing/checkpoint_manager.py` | `CheckpointManager.__init__()` | **MODIFY** | Add `_last_checkpoint_time`, `_checkpoint_interval_pages`, `_checkpoint_interval_seconds` |
| `src/preprocessing/checkpoint_manager.py` | `CheckpointManager.should_save_checkpoint()` | **ADD METHOD** | Check if checkpoint should be saved (pages OR time) |
| `src/preprocessing/checkpoint_manager.py` | `CheckpointManager.save()` | **MODIFY** | Update `_last_checkpoint_time` after save |
| `src/api/services/cache_cleanup.py` | `CacheCleanupService` | **ADD CLASS** | New service for cache cleanup |
| `src/api/main.py` | `startup_event()` | **MODIFY** | Add hourly cache cleanup background task |
| `src/api/main.py` | `run_periodic_cleanup()` | **ADD FUNCTION** | Background task for periodic cleanup |
| `src/preprocessing/staged_pipeline.py` | `StagedPipeline.process_pdf()` | **MODIFY** | Add `finally` block to call `cache_cleanup.cleanup_job_cache()` |

### Phase 3.7B: Batch Parallelization

| File | Component | Change Type | Description |
|------|-----------|-------------|-------------|
| `src/api/services/batch_manager.py` | `BatchManager._process_batch_concurrent()` | **RENAME/MODIFY** | Replace sequential loop with `asyncio.gather()` + `Semaphore` |
| `src/api/services/batch_manager.py` | `BatchManager.process_batch()` | **MODIFY** | Call `_process_batch_concurrent()` instead of `_process_batch_async()` |
| `src/api/batch_routes.py` | `stream_batch_progress()` | **MODIFY** | Add `active_files` to progress event |
| `src/api/batch_routes.py` | `stream_batch_progress()` | **MODIFY** | Aggregate progress from concurrent jobs |
| `src/api/services/job_manager.py` | Thread safety audit | **AUDIT** | Verify thread-safe access to shared state |
| `src/api/services/result_emitter.py` | Thread safety audit | **AUDIT** | Verify thread-safe access to shared state |

### Phase 3.7C: Page-Level Optimization (Option A: Mini-Batch)

| File | Component | Change Type | Description |
|------|-----------|-------------|-------------|
| `src/models/model_manager.py` | `ModelManager.infer_batch_with_container()` | **ADD METHOD** | Batch inference (4-8 images per request) |
| `src/models/model_manager.py` | `ModelManager._image_to_base64()` | **ADD METHOD** | Helper to convert image to base64 |
| `src/preprocessing/staged_pipeline.py` | `StagedPipeline.PAGE_BATCH_SIZE` | **ADD CONSTANT** | Batch size = 4-8 pages |
| `src/preprocessing/staged_pipeline.py` | `StagedPipeline.process_pdf()` | **MODIFY** | Replace page loop with batch loop |
| `src/api/services/result_emitter.py` | `ResultEmitter.emit_batch_progress()` | **MODIFY** | Emit progress per batch (not per page) |
| `baml_src/ocr.baml` | `ExtractTextOCRBatch()` | **ADD FUNCTION** | (Optional) BAML batch inference function |

### Phase 3.7C: Page-Level Optimization (Option B: Parallel Pages)

| File | Component | Change Type | Description |
|------|-----------|-------------|-------------|
| `src/models/model_manager.py` | `ModelManager.__init__()` | **MODIFY** | Add `_request_lock: asyncio.Lock` |
| `src/models/model_manager.py` | `ModelManager.infer_with_container()` | **MODIFY** | Add `async with self._request_lock:` |
| `src/preprocessing/staged_pipeline.py` | `StagedPipeline.MAX_PAGE_WORKERS` | **ADD CONSTANT** | Worker count = 4 |
| `src/preprocessing/staged_pipeline.py` | `StagedPipeline.process_pdf()` | **MODIFY** | Replace page loop with ThreadPoolExecutor |
| `src/preprocessing/staged_pipeline.py` | `StagedPipeline._process_one_page()` | **ADD METHOD** | Process single page (called from thread pool) |
| `src/api/services/result_emitter.py` | `ResultEmitter` | **MODIFY** | Handle out-of-order page completion |

---

## D. Swim Lane Derivation

Based on the interface boundaries and change list, we derive the following swim lanes:

### Phase 3.7A: I/O Optimization (3 Swim Lanes)

**Swim Lane A1: Database Layer**
- **Owner:** Database team
- **Duration:** 1-2 hours
- **Dependencies:** None (can start immediately)
- **Deliverables:**
  - `JobRepository.bulk_create_page_results()` method
  - Unit tests for bulk insert
- **Interface Freeze:** IF-0-3.7A (before A2 starts)

**Swim Lane A2: Pipeline Integration**
- **Owner:** Pipeline team
- **Duration:** 2-3 hours
- **Dependencies:** Swim Lane A1 complete, A3 interface defined
- **Deliverables:**
  - Output buffering in `StagedPipeline`
  - Call `bulk_create_page_results()` instead of individual inserts
  - Adaptive checkpointing integration
  - Call `cache_cleanup.cleanup_job_cache()` in finally block
- **Interface Freeze:** IF-0-3.7A (waits for A1)

**Swim Lane A3: Cleanup Service**
- **Owner:** Infrastructure team
- **Duration:** 1-2 hours
- **Dependencies:** None (can start in parallel with A1)
- **Deliverables:**
  - `CacheCleanupService` class
  - `run_periodic_cleanup()` background task
  - Integration in `main.py` startup
- **Interface Freeze:** IF-0-3.7A (before A2 starts)

**Parallelization:**
- A1 and A3 can run in parallel (independent)
- A2 waits for A1 and A3 to complete

---

### Phase 3.7B: Batch Parallelization (2 Swim Lanes)

**Swim Lane B1: Batch Manager Concurrency**
- **Owner:** Backend team
- **Duration:** 4-5 hours
- **Dependencies:** None (can start immediately)
- **Deliverables:**
  - `BatchManager._process_batch_concurrent()` method
  - Thread safety audit for `JobManager`, `ResultEmitter`
  - Unit tests for concurrent processing
- **Interface Freeze:** IF-0-3.7B (before B2 starts)

**Swim Lane B2: Progress Aggregation**
- **Owner:** API team
- **Duration:** 2-3 hours
- **Dependencies:** Swim Lane B1 complete
- **Deliverables:**
  - Update `stream_batch_progress()` to handle concurrent jobs
  - Add `active_files` to progress events
  - Integration tests
- **Interface Freeze:** IF-0-3.7B (waits for B1)

**Parallelization:**
- B1 must complete before B2 starts (sequential dependency)

---

### Phase 3.7C: Page-Level Optimization (2 Swim Lanes - Option A)

**Swim Lane C1: Model Manager Batch Inference**
- **Owner:** Model team
- **Duration:** 4-5 hours
- **Dependencies:** Container `/infer_batch` API ready (external blocker)
- **Deliverables:**
  - `ModelManager.infer_batch_with_container()` method
  - Container API integration tests
  - Fallback to sequential if batch not supported
- **Interface Freeze:** IF-0-3.7C (before C2 starts)

**Swim Lane C2: Pipeline Batch Processing**
- **Owner:** Pipeline team
- **Duration:** 3-4 hours
- **Dependencies:** Swim Lane C1 complete
- **Deliverables:**
  - Replace page loop with batch loop in `StagedPipeline`
  - Update progress emission (per batch, not per page)
  - Integration tests
- **Interface Freeze:** IF-0-3.7C (waits for C1)

**Parallelization:**
- C1 must complete before C2 starts (sequential dependency)
- **BLOCKER:** Container API `/infer_batch` must be ready before C1 starts

---

### Phase 3.7C: Page-Level Optimization (2 Swim Lanes - Option B)

**Swim Lane C1: Model Manager Thread Safety**
- **Owner:** Model team
- **Duration:** 2-3 hours
- **Dependencies:** None (can start immediately)
- **Deliverables:**
  - Add `_request_lock` to `ModelManager`
  - Thread-safe `infer_with_container()`
  - Concurrency tests
- **Interface Freeze:** IF-0-3.7C (before C2 starts)

**Swim Lane C2: Pipeline Parallel Processing**
- **Owner:** Pipeline team
- **Duration:** 4-5 hours
- **Dependencies:** Swim Lane C1 complete
- **Deliverables:**
  - Replace page loop with ThreadPoolExecutor
  - Handle out-of-order page completion
  - Integration tests
- **Interface Freeze:** IF-0-3.7C (waits for C1)

**Parallelization:**
- C1 must complete before C2 starts (sequential dependency)

---

## Swim Lane Diagram (Phase 3.7A)

```
Time →
0h    1h    2h    3h    4h    5h    6h
├─────┼─────┼─────┼─────┼─────┼─────┤

A1 (DB Layer)
├─────────┤ (1-2h)
│ bulk_create_page_results()
│ unit tests
└─────────→ IF-0-3.7A FREEZE

A3 (Cleanup)
├─────────┤ (1-2h)
│ CacheCleanupService
│ background task
└─────────→ IF-0-3.7A FREEZE

          ↓ Wait for A1 + A3

A2 (Pipeline)
          ├─────────────────┤ (2-3h)
          │ output buffering
          │ bulk DB inserts
          │ adaptive checkpoints
          │ cleanup integration
          └─────────────────→ DONE

Total: 4-6 hours (2-3h if parallelized)
```

---

## Swim Lane Diagram (Phase 3.7B)

```
Time →
0h    1h    2h    3h    4h    5h    6h    7h    8h
├─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤

B1 (Batch Manager)
├───────────────────────┤ (4-5h)
│ _process_batch_concurrent()
│ thread safety audit
│ unit tests
└───────────────────────→ IF-0-3.7B FREEZE

                        ↓ Wait for B1

                        B2 (Progress)
                        ├─────────────┤ (2-3h)
                        │ aggregate progress
                        │ active_files
                        │ integration tests
                        └─────────────→ DONE

Total: 6-8 hours (sequential)
```

---

## Swim Lane Diagram (Phase 3.7C - Option A)

```
Time →
0h    1h    2h    3h    4h    5h    6h    7h    8h    9h    10h   11h   12h
├─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤

BLOCKER: Container /infer_batch API ready
├─────────────────────┤ (? hours, external)
└───────────────────→ API Ready

                      C1 (Model Manager)
                      ├───────────────────┤ (4-5h)
                      │ infer_batch_with_container()
                      │ container integration
                      │ tests
                      └───────────────────→ IF-0-3.7C FREEZE

                                          ↓ Wait for C1

                                          C2 (Pipeline)
                                          ├─────────────┤ (3-4h)
                                          │ batch loop
                                          │ progress
                                          │ integration tests
                                          └─────────────→ DONE

Total: 7-9 hours (after container ready)
```

---

## E. Implementation Plan

### Phase 3.7A: I/O Optimization (4-6 hours)

#### Step 1: Database Layer (Swim Lane A1) - 1-2 hours

**Owner:** Database team
**Dependencies:** None

**Tasks:**
1. Implement `JobRepository.bulk_create_page_results()` method
   - Accept list of page result dicts
   - Build bulk INSERT SQL query
   - Use Supabase batch insert API
   - Handle transaction (all-or-nothing)
   - Return list of created records

2. Write unit tests
   - Test bulk insert 10 pages
   - Test bulk insert 100 pages
   - Test empty list (ValueError)
   - Test invalid job_id (ValueError)
   - Test duplicate page_num (UPDATE behavior)
   - Test transaction rollback on error

3. Freeze interface (IF-0-3.7A)

**Acceptance Criteria:**
- ✅ Method signature matches interface contract
- ✅ All unit tests pass
- ✅ Performance: 100 pages insert in <200ms
- ✅ Interface documented and frozen

---

#### Step 2: Cleanup Service (Swim Lane A3) - 1-2 hours

**Owner:** Infrastructure team
**Dependencies:** None (parallel with A1)

**Tasks:**
1. Create `src/api/services/cache_cleanup.py`
   - Implement `CacheCleanupService` class
   - Implement `cleanup_expired_files()` method
   - Implement `cleanup_job_cache()` method
   - Add logging (INFO for deletions, WARNING for errors)

2. Integrate into `src/api/main.py`
   - Add `run_periodic_cleanup()` background task
   - Schedule hourly cleanup on startup
   - Handle graceful shutdown

3. Write unit tests
   - Test cleanup expired files
   - Test cleanup specific job
   - Test handles errors gracefully (no exceptions)

4. Freeze interface (IF-0-3.7A)

**Acceptance Criteria:**
- ✅ Service implementation matches interface contract
- ✅ Background task runs every hour
- ✅ Never raises exceptions (safe for background tasks)
- ✅ Logs deletions at INFO level

---

#### Step 3: Pipeline Integration (Swim Lane A2) - 2-3 hours

**Owner:** Pipeline team
**Dependencies:** A1 and A3 complete, interfaces frozen

**Tasks:**
1. Add output buffering to `StagedPipeline.process_pdf()`
   - Add `OUTPUT_BUFFER_SIZE = 10` constant
   - Create `output_buffer: List[str] = []`
   - Append page text to buffer
   - Flush buffer every 10 pages
   - Flush remaining pages at end

2. Implement `_flush_output_buffer()` method
   - Write buffered pages to output file (append mode)
   - Log flush operation (DEBUG level)

3. Replace individual DB inserts with bulk insert
   - Create `page_results_buffer: List[Dict] = []`
   - Append page result to buffer
   - Call `job_repo.bulk_create_page_results()` every 10 pages
   - Flush remaining pages at end

4. Integrate adaptive checkpointing
   - Update `CheckpointManager.__init__()` with new fields
   - Implement `should_save_checkpoint()` method
   - Update `save()` to reset timestamp
   - Call `should_save_checkpoint()` before each checkpoint

5. Add cache cleanup to finally block
   - Import `CacheCleanupService`
   - Call `cache_cleanup.cleanup_job_cache(job_id)` in finally

6. Write integration tests
   - Test 50-page PDF: verify ~5 output writes (not 50)
   - Test 50-page PDF: verify ~5 DB bulk inserts (not 50)
   - Test checkpoint saved every 5 pages OR 30 seconds
   - Test cache cleanup on job completion
   - Test cache cleanup on job failure

**Acceptance Criteria:**
- ✅ Output writes: 10x reduction (100 pages = 10 writes)
- ✅ DB inserts: 10x reduction (100 pages = 10 bulk inserts)
- ✅ Checkpoints: 5x reduction (100 pages = 20 checkpoints)
- ✅ Cache cleanup: always runs (even on failure)
- ✅ All integration tests pass

---

### Phase 3.7B: Batch Parallelization (6-8 hours)

#### Step 1: Batch Manager Concurrency (Swim Lane B1) - 4-5 hours

**Owner:** Backend team
**Dependencies:** None

**Tasks:**
1. Rename `_process_batch_async()` to `_process_batch_concurrent()`

2. Replace sequential loop with concurrent processing
   - Import `asyncio.Semaphore, asyncio.gather`
   - Get `max_concurrent = job_manager.max_concurrent_jobs`
   - Create `semaphore = Semaphore(max_concurrent)`
   - Define `async def process_one_doc(file_id, idx)`
   - Acquire semaphore in `process_one_doc()`
   - Check cancellation before each job
   - Update batch progress (thread-safe with lock)
   - Build task list: `[process_one_doc(fid, i) for i, fid in enumerate(file_ids)]`
   - Execute: `results = await gather(*tasks, return_exceptions=True)`
   - Handle results and errors

3. Thread safety audit
   - Audit `JobManager` for shared state
   - Audit `ResultEmitter` for shared state
   - Add locks if needed (e.g., `asyncio.Lock` for dict updates)

4. Write unit tests
   - Test 10-doc batch with max_concurrent=2
   - Verify 2 jobs run simultaneously (mock time.time())
   - Test error handling: 1 job fails, others continue
   - Test cancellation: ongoing jobs finish, remaining skipped

5. Freeze interface (IF-0-3.7B)

**Acceptance Criteria:**
- ✅ Concurrency limited to `max_concurrent_jobs`
- ✅ Failed jobs don't block other jobs
- ✅ Cancellation works correctly
- ✅ Thread safety verified (no race conditions)
- ✅ All unit tests pass

---

#### Step 2: Progress Aggregation (Swim Lane B2) - 2-3 hours

**Owner:** API team
**Dependencies:** B1 complete, interface frozen

**Tasks:**
1. Update `stream_batch_progress()` in `batch_routes.py`
   - Add `active_files` calculation
   - Query `job_manager` for jobs in "processing" state
   - Aggregate progress from concurrent jobs
   - Use `batch_manager.batch_lock` for thread safety

2. Update progress event schema
   - Add `active_files: int` field
   - Document schema in docstring

3. Write integration tests
   - Test progress events with concurrent jobs
   - Verify `active_files` reflects concurrent count
   - Test progress monotonically increases
   - Test final event emitted on completion

**Acceptance Criteria:**
- ✅ `active_files` accurately reflects concurrent jobs
- ✅ Progress aggregation is thread-safe
- ✅ All integration tests pass

---

### Phase 3.7C: Page-Level Optimization (Option A) (7-9 hours + container work)

#### External Blocker: Container API (? hours)

**Owner:** External (GPU container team)
**Dependencies:** None

**Tasks:**
1. Implement `/infer_batch` endpoint in DeepSeek container
   - Accept `images_base64: List[str]` (1-16 images)
   - Process batch inference
   - Return `results: List[Dict]` (same order as input)

2. Implement `/infer_batch` endpoint in Qwen container
   - Same as above

3. Document API contract
   - Request/response schema
   - Performance characteristics
   - Concurrency limits

**Acceptance Criteria:**
- ✅ Container accepts 1-16 images per request
- ✅ Returns results in same order as input
- ✅ Performance: 8 images in ~2.5s (vs 12s sequential)
- ✅ Thread-safe: handles concurrent requests

---

#### Step 1: Model Manager Batch Inference (Swim Lane C1) - 4-5 hours

**Owner:** Model team
**Dependencies:** Container API ready

**Tasks:**
1. Implement `ModelManager.infer_batch_with_container()` method
   - Accept `images: List[Image.Image]`
   - Convert all images to base64
   - Build batch request
   - Call container `/infer_batch` endpoint
   - Parse batch response
   - Return `List[OCRResult]`

2. Add fallback to sequential processing
   - If container returns 404 (endpoint not found)
   - Log warning and fall back to individual `infer_with_container()` calls

3. Write integration tests
   - Test batch inference with 4, 8, 16 images
   - Test fallback to sequential if batch not supported
   - Test error handling (empty list, invalid images)
   - Measure performance vs sequential

4. Freeze interface (IF-0-3.7C)

**Acceptance Criteria:**
- ✅ Method signature matches interface contract
- ✅ Returns results in same order as input
- ✅ Fallback works if batch not supported
- ✅ Performance: 3-4x speedup vs sequential
- ✅ All integration tests pass

---

#### Step 2: Pipeline Batch Processing (Swim Lane C2) - 3-4 hours

**Owner:** Pipeline team
**Dependencies:** C1 complete, interface frozen

**Tasks:**
1. Replace page loop with batch loop in `StagedPipeline.process_pdf()`
   - Add `PAGE_BATCH_SIZE = 4` constant (configurable)
   - Loop: `for batch_start in range(0, total_pages, PAGE_BATCH_SIZE)`
   - Extract batch of images
   - Call `model_manager.infer_batch_with_container(images)`
   - Process each result (merge, emit progress, buffer output)

2. Update progress emission
   - Emit progress per batch (not per page)
   - Calculate: `progress = (batch_end / total_pages) * 100`

3. Write integration tests
   - Test 50-page PDF with BATCH_SIZE=4
   - Verify ~13 batch requests (vs 50 individual)
   - Measure total processing time (3-4x speedup)
   - Verify OCR quality unchanged (compare results)

**Acceptance Criteria:**
- ✅ Batch processing works correctly
- ✅ Progress tracking accurate
- ✅ OCR quality unchanged
- ✅ Performance: 3-4x speedup for large documents
- ✅ All integration tests pass

---

### Phase 3.7C: Page-Level Optimization (Option B) (6-8 hours)

#### Step 1: Model Manager Thread Safety (Swim Lane C1) - 2-3 hours

**Owner:** Model team
**Dependencies:** None

**Tasks:**
1. Add `_request_lock` to `ModelManager.__init__()`
   - `self._request_lock = asyncio.Lock()`

2. Update `infer_with_container()` to use lock
   - Wrap inference logic: `async with self._request_lock:`

3. Write concurrency tests
   - Test 4 parallel calls to `infer_with_container()`
   - Verify thread safety (no race conditions)
   - Measure performance vs sequential

4. Freeze interface (IF-0-3.7C)

**Acceptance Criteria:**
- ✅ Thread-safe concurrent requests
- ✅ No performance degradation (lock overhead minimal)
- ✅ All concurrency tests pass

---

#### Step 2: Pipeline Parallel Processing (Swim Lane C2) - 4-5 hours

**Owner:** Pipeline team
**Dependencies:** C1 complete, interface frozen

**Tasks:**
1. Replace page loop with ThreadPoolExecutor in `StagedPipeline.process_pdf()`
   - Add `MAX_PAGE_WORKERS = 4` constant
   - Define `async def _process_one_page(page_num, page_data)`
   - Build task list: `[_process_one_page(i, page) for i, page in enumerate(pages)]`
   - Execute: `results = await gather(*tasks)`
   - Sort results by page number (may complete out of order)
   - Write results to output

2. Handle out-of-order completion
   - Buffer results until all pages in sequence completed
   - Emit progress as pages complete

3. Write integration tests
   - Test 50-page PDF with 4 workers
   - Verify 4 pages processed concurrently
   - Measure total processing time (4-8x speedup)
   - Verify OCR quality unchanged

**Acceptance Criteria:**
- ✅ Parallel processing works correctly
- ✅ Results written in correct order
- ✅ Progress tracking accurate
- ✅ Performance: 4-8x speedup for large documents
- ✅ All integration tests pass

---

## F. Testing Strategy

### Unit Tests

**Phase 3.7A:**
- `test_job_repository.py::test_bulk_create_page_results()`
- `test_job_repository.py::test_bulk_create_page_results_empty_list()`
- `test_job_repository.py::test_bulk_create_page_results_invalid_job_id()`
- `test_checkpoint_manager.py::test_should_save_checkpoint_pages()`
- `test_checkpoint_manager.py::test_should_save_checkpoint_time()`
- `test_cache_cleanup.py::test_cleanup_expired_files()`
- `test_cache_cleanup.py::test_cleanup_job_cache()`

**Phase 3.7B:**
- `test_batch_manager.py::test_process_batch_concurrent()`
- `test_batch_manager.py::test_concurrent_error_handling()`
- `test_batch_manager.py::test_concurrent_cancellation()`

**Phase 3.7C (Option A):**
- `test_model_manager.py::test_infer_batch_with_container()`
- `test_model_manager.py::test_infer_batch_fallback()`

**Phase 3.7C (Option B):**
- `test_model_manager.py::test_concurrent_requests()`

---

### Integration Tests

**Phase 3.7A:**
```bash
# Test output buffering and bulk DB inserts
uv run pytest tests/integration/test_phase_3_7a.py::test_output_buffering -v
uv run pytest tests/integration/test_phase_3_7a.py::test_bulk_db_inserts -v
uv run pytest tests/integration/test_phase_3_7a.py::test_adaptive_checkpoints -v
uv run pytest tests/integration/test_phase_3_7a.py::test_cache_cleanup -v
```

**Phase 3.7B:**
```bash
# Test concurrent batch processing
uv run pytest tests/integration/test_phase_3_7b.py::test_concurrent_batch -v
uv run pytest tests/integration/test_phase_3_7b.py::test_progress_aggregation -v
```

**Phase 3.7C:**
```bash
# Test page-level optimization
uv run pytest tests/integration/test_phase_3_7c.py::test_batch_inference -v
uv run pytest tests/integration/test_phase_3_7c.py::test_parallel_pages -v
```

---

### Performance Benchmarks

**Baseline (Pre-Phase 3.7):**
```bash
# Measure current performance
uv run python tests/benchmarks/benchmark_phase_3_7.py --baseline

Expected output:
- 100-page document: 3-7 minutes
- 100-doc batch: 16-33 hours
- Disk I/O: 100 writes, 100 DB inserts, 100 checkpoints
```

**Phase 3.7A (Post-I/O Optimization):**
```bash
# Measure I/O improvements
uv run python tests/benchmarks/benchmark_phase_3_7.py --phase-3-7a

Expected output:
- Disk I/O: 10 writes (10x reduction)
- DB inserts: 10 bulk inserts (10x reduction)
- Checkpoints: 20 saves (5x reduction)
- Cache cleanup: 0 orphaned directories after 24 hours
```

**Phase 3.7B (Post-Batch Parallelization):**
```bash
# Measure batch speedup
uv run python tests/benchmarks/benchmark_phase_3_7.py --phase-3-7b

Expected output:
- 100-doc batch: 8-16 hours (2x speedup)
- Concurrent jobs: 2 active at any time
```

**Phase 3.7C (Post-Page Optimization):**
```bash
# Measure page-level speedup
uv run python tests/benchmarks/benchmark_phase_3_7.py --phase-3-7c

Expected output:
- 100-page document: 45-90 seconds (3-5x speedup)
- GPU utilization: >80% during processing
```

**Overall (All Phases):**
```bash
# Measure end-to-end improvement
uv run python tests/benchmarks/benchmark_phase_3_7.py --all

Expected output:
- 100-page document: 45-90 seconds (was 3-7 minutes) = 6-10x
- 100-doc batch: 8-16 hours (was 16-33 hours) = 2x
- Disk I/O: 10x reduction
- DB transactions: 10x reduction
```

---

### End-to-End Tests

**Test Scenario 1: Large Document**
```bash
# Upload 100-page PDF
# Submit job
# Monitor progress
# Verify:
# - ~10 output writes (not 100)
# - ~10 DB bulk inserts (not 100)
# - ~20 checkpoints (not 100)
# - Processing time < 2 minutes (was 5-7 minutes)
# - Cache cleaned up after completion
```

**Test Scenario 2: Batch Processing**
```bash
# Upload 20 documents (10-20 pages each)
# Submit batch job
# Monitor progress
# Verify:
# - 2 documents processing concurrently
# - active_files = 2 during processing
# - Batch completes in ~20 minutes (was ~40 minutes)
# - All results correct
```

**Test Scenario 3: Job Failure**
```bash
# Submit job
# Kill backend mid-processing
# Verify:
# - Cache directory cleaned up
# - No orphaned files
# - Checkpoint saved correctly
```

---

## G. Rollback Plan

### Phase 3.7A Rollback

**If bugs found:**
```bash
# Revert to individual writes/inserts
git revert <phase-3.7a-commits>

# OR: Feature flag to disable buffering
# config/settings.py
ENABLE_OUTPUT_BUFFERING = False
ENABLE_BULK_DB_INSERTS = False
ENABLE_ADAPTIVE_CHECKPOINTS = False
```

**Rollback steps:**
1. Set feature flags to `False`
2. Restart backend
3. Verify existing functionality works
4. Fix bugs
5. Re-enable feature flags

---

### Phase 3.7B Rollback

**If concurrency issues:**
```bash
# Revert to sequential batch processing
git revert <phase-3.7b-commits>

# OR: Feature flag to disable concurrency
# config/settings.py
ENABLE_CONCURRENT_BATCH_PROCESSING = False
```

**Rollback steps:**
1. Set feature flag to `False`
2. Restart backend
3. Verify sequential processing works
4. Fix thread safety issues
5. Re-enable feature flag

---

### Phase 3.7C Rollback

**If batch inference or parallelization issues:**
```bash
# Revert to sequential page processing
git revert <phase-3.7c-commits>

# OR: Feature flag to disable optimization
# config/settings.py
ENABLE_PAGE_BATCH_INFERENCE = False  # Option A
ENABLE_PARALLEL_PAGE_PROCESSING = False  # Option B
```

**Rollback steps:**
1. Set feature flag to `False`
2. Restart backend
3. Verify sequential processing works
4. Fix optimization issues
5. Re-enable feature flag

---

## H. Success Criteria

### Phase 3.7A Success Criteria

- ✅ 10x reduction in disk I/O operations (100 pages = 10 writes)
- ✅ 10x reduction in database transactions (100 pages = 10 bulk inserts)
- ✅ 5x reduction in checkpoint writes (100 pages = 20 checkpoints)
- ✅ Zero orphaned cache directories after 24 hours
- ✅ No performance degradation
- ✅ All existing tests pass

### Phase 3.7B Success Criteria

- ✅ 2x batch processing throughput (100 docs in 100 min vs 200 min)
- ✅ Batch progress accurately reflects concurrent jobs
- ✅ No race conditions or deadlocks
- ✅ Failed jobs don't block other jobs
- ✅ System resource usage within limits

### Phase 3.7C Success Criteria

- ✅ 3-5x speedup for large documents (50+ pages)
- ✅ OCR quality unchanged (same accuracy as sequential)
- ✅ Progress tracking accurate during batch/parallel processing
- ✅ No memory leaks or resource exhaustion
- ✅ GPU utilization optimized (>80% during processing)

### Overall Phase 3.7 Success Criteria

- ✅ 6-10x faster end-to-end processing
- ✅ All sub-phases complete and tested
- ✅ No breaking changes to existing functionality
- ✅ Performance benchmarks documented
- ✅ Ready for Phase 4 database-only migration

---

## I. Decision Points

### Decision 1: Phase 3.7C - Option A vs Option B?

**Context:** Two approaches for page-level optimization

**Option A: Mini-Batch Inference**
- Pros: Better GPU utilization, lower risk, simpler
- Cons: Requires container API changes (external blocker)
- Best for: GPU-bound workloads, batch inference support

**Option B: Parallel Page Processing**
- Pros: No container changes, easier to implement
- Cons: Higher risk of race conditions, thread safety complexity
- Best for: I/O-bound workloads, multiple GPU instances

**Recommendation:** Start with Option A (mini-batch), fall back to Option B if container API not ready

**Decision criteria:**
1. Check if container API supports `/infer_batch`
2. If yes → Implement Option A
3. If no → Implement Option B as interim solution, plan Option A for later

---

### Decision 2: Output Buffer Size

**Context:** How many pages to buffer before flushing?

**Options:**
- 5 pages: Lower memory, more frequent writes
- 10 pages: Balanced (recommended)
- 20 pages: Higher memory, fewer writes

**Recommendation:** 10 pages (balance between memory and I/O)

**Rationale:**
- 10 pages × 5KB/page = 50KB buffer (negligible memory)
- 100-page doc = 10 writes (10x reduction)
- Checkpoint interval = 5 pages (2 checkpoints per buffer flush)

---

### Decision 3: Page Batch Size (Option A)

**Context:** How many pages per batch inference request?

**Options:**
- 4 pages: Lower GPU memory, more requests
- 8 pages: Balanced (recommended)
- 16 pages: Higher GPU memory, fewer requests

**Recommendation:** 8 pages (balance between GPU memory and request overhead)

**Rationale:**
- 8 images @ 1024px fits in 16GB GPU RAM
- 100-page doc = 13 batch requests (vs 100 individual)
- 8× speedup potential (vs sequential)

---

## J. Next Steps

### Immediate Actions (Today)

1. **Review this plan** with team leads
2. **Decide on Phase 3.7C approach** (Option A vs B)
3. **Assign swim lane owners** (A1, A2, A3, B1, B2, C1, C2)
4. **Check container API status** (blocker for Option A)
5. **Create feature flags** for rollback capability

### Week 1: Phase 3.7A (I/O Optimization)

**Day 1:**
- Swim Lane A1: Implement `bulk_create_page_results()`
- Swim Lane A3: Implement `CacheCleanupService`

**Day 2:**
- Swim Lane A2: Integrate buffering, bulk inserts, checkpoints
- Integration testing

**Day 3:**
- Performance benchmarking
- Bug fixes
- Documentation updates

### Week 2: Phase 3.7B (Batch Parallelization)

**Day 1-2:**
- Swim Lane B1: Implement concurrent batch processing
- Thread safety audit

**Day 3:**
- Swim Lane B2: Implement progress aggregation
- Integration testing
- Performance benchmarking

### Week 3: Phase 3.7C (Page-Level Optimization)

**Day 1-2:**
- Swim Lane C1: Implement batch inference or thread safety
- Container integration testing

**Day 3-4:**
- Swim Lane C2: Implement pipeline optimization
- Integration testing
- Performance benchmarking

**Day 5:**
- End-to-end testing
- Documentation
- Phase 3.7 complete review

---

## K. Appendix

### Glossary

- **Bulk Insert:** Database operation that inserts multiple rows in single transaction (faster than individual INSERTs)
- **Output Buffering:** Accumulating data in memory before writing to disk (reduces I/O operations)
- **Adaptive Checkpointing:** Saving checkpoints based on time OR page count (whichever comes first)
- **Mini-Batch Inference:** Sending multiple images in single GPU request (better GPU utilization)
- **Parallel Page Processing:** Processing multiple pages concurrently using ThreadPoolExecutor
- **Interface Freeze:** Point at which interface contracts cannot change (allows dependent work to proceed)
- **Swim Lane:** Independent work stream that can be executed in parallel with other swim lanes

### References

- [MASTER_ROADMAP.md](MASTER_ROADMAP.md) - Source specification
- [multi-page-parsing-architecture.md](multi-page-parsing-architecture.md) - Performance analysis
- [PHASE_3_IMPLEMENTATION_PLAN.md](PHASE_3_IMPLEMENTATION_PLAN.md) - Phase 3 context

---

**END OF IMPLEMENTATION PLAN**
