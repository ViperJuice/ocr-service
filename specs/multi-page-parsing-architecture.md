# Multi-Page Parsing Architecture

**Document Version:** 1.0
**Date:** 2025-11-16
**Status:** Analysis Complete

## Table of Contents

- [Overview](#overview)
- [Architecture Summary](#architecture-summary)
- [Request Flow](#request-flow)
- [Processing Pipeline](#processing-pipeline)
- [Data Persistence Strategy](#data-persistence-strategy)
- [Page Tracking and Reassembly](#page-tracking-and-reassembly)
- [Real-Time Streaming](#real-time-streaming)
- [Batch Processing](#batch-processing)
- [Resume Capability](#resume-capability)
- [File Storage Patterns](#file-storage-patterns)
- [Configuration](#configuration)
- [Critical File References](#critical-file-references)
- [Architecture Analysis](#architecture-analysis)
- [Recommendations](#recommendations)

---

## Overview

This document provides a comprehensive analysis of how the OCR service handles multi-page document processing, including the complete data flow from upload to final merged result, persistence mechanisms, streaming architecture, and recommendations for optimization.

### Key Characteristics

- **Processing Model:** 2-stage sequential pipeline (OCR → Merge)
- **Page Processing:** Individual pages, no batching
- **Data Persistence:** Three-layer system (filesystem, memory, database)
- **Reassembly:** Sequential append to single output file
- **Streaming:** Server-Sent Events (SSE) with asyncio queues
- **Concurrency:** Documents processed sequentially in batches
- **Resume:** Checkpoint-based recovery system

---

## Architecture Summary

### Processing Model: Staged Sequential Pipeline

The system uses a **2-stage sequential pipeline** where each page is processed individually:

```
┌─────────────────────────────────────────────────────────┐
│                   STAGE 1: OCR EXTRACTION                │
│                     (0-60% progress)                      │
│                                                           │
│  For each page sequentially:                             │
│    1. Extract page to image                              │
│    2. Send to DeepSeek-OCR container                     │
│    3. Extract text + metadata                            │
│    4. Save to cache: page_XXXX.json                      │
│    5. Update checkpoint                                  │
│    6. Emit SSE event (ocr_page_complete)                 │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                 STAGE 2: MERGE/REFINEMENT                │
│                     (60-90% progress)                     │
│                                                           │
│  For each page sequentially:                             │
│    1. Load OCR result from cache                         │
│    2. Compare with embedded PDF text                     │
│    3. Send to Qwen3-VL container                         │
│    4. Merge/refine text                                  │
│    5. Append to final output file                        │
│    6. Update checkpoint                                  │
│    7. Emit SSE event (merge_page_complete)               │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                    CLEANUP & COMPLETION                   │
│                     (90-100% progress)                    │
│                                                           │
│    1. Clear intermediate cache                           │
│    2. Clear checkpoint files                             │
│    3. Update job status to COMPLETED                     │
│    4. Emit SSE event (job_complete)                      │
└─────────────────────────────────────────────────────────┘
```

**Critical Finding:** There is **NO batching** at the page level - everything is strictly sequential, page-by-page processing.

**Location:** `src/preprocessing/staged_pipeline.py:332-731`

---

## Request Flow

### API Endpoints

#### Single Document (Multi-Page PDF)

**Endpoint:** `POST /api/v1/process/jobs`
**Location:** `src/api/processing_routes.py:98-174`

**Request Format:**
```json
{
  "file_id": "uuid",
  "model": "deepseek-ocr",
  "prompt_type": "markdown",
  "custom_prompts": {
    "ocr_prompt": "...",
    "merge_prompt": "..."
  },
  "processing_options": {
    "dpi": 300,
    "method": "auto|extract|ocr|hybrid",
    "start_page": 1,
    "end_page": 50,
    "staged_pipeline": true,
    "prefer_quality": true
  },
  "output_format": "markdown|text|json"
}
```

#### Batch Processing (Multiple Documents)

**Endpoint:** `POST /api/v1/batch/process`
**Location:** `src/api/batch_routes.py:89-157`

**Request Format:**
```json
{
  "directory_id": "uuid",
  "model": "deepseek-ocr",
  "prompt_type": "markdown",
  "custom_prompts": {},
  "processing_options": {
    "dpi": 300,
    "method": "auto"
  },
  "output_format": "markdown"
}
```

---

## Processing Pipeline

### Complete End-to-End Flow

```
1. FILE UPLOAD
   POST /api/v1/process/upload
   ├─ UploadFile (PDF)
   ├─ FileManager.save_upload()
   │  ├─ Generate file_id (UUID)
   │  ├─ Extract page count from PDF
   │  ├─ Save to: /tmp/{file_id}/original
   │  └─ Return FileMetadata
   └─ Optional: Write to Supabase files table

2. JOB SUBMISSION
   POST /api/v1/process/jobs
   ├─ Request: file_id, model, prompts, options
   ├─ JobManager.create_job()
   │  ├─ Generate job_id (UUID)
   │  ├─ Validate file exists
   │  ├─ Create in-memory Job object
   │  └─ Optional: Write to Supabase jobs table
   └─ JobManager.start_job()
      └─ Spawn processing thread (background)

3. PDF EXTRACTION (ASYNC THREAD)
   ├─ PDFHandler.extract_hybrid_data()
   │  ├─ Read PDF file
   │  ├─ For each page:
   │  │  ├─ Extract embedded text (if exists)
   │  │  ├─ Render to image at specified DPI
   │  │  └─ Store as (embedded_text, image, has_text) tuple
   │  └─ Return: List[Tuple]
   └─ Check for resume: load checkpoint if exists

4. STAGE 1: OCR EXTRACTION (INDIVIDUAL PAGES)
   StagedPipelineProcessor._run_ocr_stage()
   ├─ For page_idx in range(start_page, total_pages):
   │  ├─ page_num = page_idx + 1
   │  ├─ embedded_text, image, has_text = pages_data[page_idx]
   │  ├─ [CONTAINER INFERENCE]
   │  │  ├─ If BAML: baml_ocr_service.extract_text_ocr(image)
   │  │  └─ Else: model_manager.infer_with_container("deepseek-ocr", image)
   │  ├─ ocr_text = model_result.text
   │  ├─ Intermediate Cache: cache.save_ocr_result(page_idx, OCRPageResult)
   │  │  └─ File: {job_dir}.ocr_cache/page_XXXX.json
   │  ├─ Checkpoint: checkpoint_manager.save_stage_progress("ocr", page_idx)
   │  ├─ Database: update_job_progress(progress_pct=0-60, pages_completed)
   │  ├─ ResultEmitter: emit_ocr_page(page_num, ocr_text)  [SSE]
   │  └─ Callback: progress_callback(progress_pct, page_idx+1, "ocr")
   └─ ResultEmitter: emit_stage_complete("ocr")

5. STAGE TRANSITION
   ├─ Checkpoint: complete_stage("ocr")
   └─ Progress: 60% complete

6. STAGE 2: MERGE/REFINEMENT (INDIVIDUAL PAGES)
   StagedPipelineProcessor._run_merge_stage()
   ├─ For page_idx in range(start_page, total_pages):
   │  ├─ page_num = page_idx + 1
   │  ├─ ocr_result = cache.load_ocr_result(page_idx)
   │  ├─ embedded_text = pages_data[page_idx][0]
   │  ├─ Build merge_prompt (compare embedded + OCR text)
   │  ├─ [CONTAINER INFERENCE]
   │  │  ├─ If BAML: baml_ocr_service.merge_texts(...)
   │  │  └─ Else: model_manager.infer_with_container("qwen3-vl-8b", ...)
   │  ├─ merged_text = model_result.text
   │  ├─ Output File: _write_page_result(output_path, merged_text, append)
   │  │  └─ File: /output/{job_id}/result.markdown (append mode)
   │  ├─ Checkpoint: save_stage_progress("merge", page_idx)
   │  ├─ Database: update_job_progress(progress_pct=60-90, pages_completed)
   │  ├─ ResultEmitter: emit_merge_page(page_num, merged_text)  [SSE]
   │  └─ Callback: progress_callback(progress_pct, page_idx+1, "merge")
   └─ ResultEmitter: emit_stage_complete("merge")

7. CLEANUP & COMPLETION
   ├─ Checkpoint: clear()  [Delete checkpoint file]
   ├─ IntermediateCache: clear()  [Delete OCR cache dir]
   ├─ System Monitor: stop()
   ├─ Job Status: COMPLETED
   ├─ Final Progress: 100%
   ├─ ResultEmitter: emit_job_complete()
   ├─ Database: update_job_status(status="completed", completed_at=NOW)
   └─ Return: { total_pages, total_time, output_path, result_url }

8. RESULT RETRIEVAL
   GET /api/v1/process/jobs/{job_id}/result
   ├─ JobManager.get_job_result()
   │  ├─ Read output file
   │  ├─ Load OCR cache (optional deepseek_ocr_content)
   │  └─ Return: { format, content, total_pages, processing_time, ... }
   └─ Response: Complete merged document text
```

---

## Data Persistence Strategy

### Three-Layer Storage System

#### 1. Local Filesystem (Primary)

**Base Directories:**
```
/tmp/ocr_api/uploads/     → Original uploaded files
/tmp/ocr_api/processing/  → Transient processing data
/tmp/ocr_api/output/      → Final results and caches
```

**Job Output Structure:**
```
/tmp/ocr_api/output/{job_id}/
├── result.markdown                   # Final merged output
├── result.markdown.ocr_cache/        # Intermediate cache
│   ├── page_0000.json               # {"page_num": 0, "ocr_text": "...", ...}
│   ├── page_0001.json
│   └── page_XXXX.json               # Per-page OCR results
└── .checkpoint                       # Resume capability data
```

**Configuration:** `config/settings.py`
```python
api_temp_directory = "/tmp/ocr_api/uploads"
api_processing_directory = "/tmp/ocr_api/processing"
api_output_directory = "/tmp/ocr_api/output"
temp_file_expiry_hours = 6  # Auto-delete after 6 hours
```

**OCR Cache Structure:**
**Location:** `src/preprocessing/intermediate_cache.py`

```json
{
  "page_num": 0,
  "ocr_text": "Extracted text content...",
  "method": "ocr|embedded|hybrid",
  "processing_time": 1.234,
  "metadata": {
    "model": "deepseek-ocr",
    "resolution_mode": "high",
    "crop_mode": "none"
  }
}
```

#### 2. In-Memory State

**Job Manager:**
**Location:** `src/api/services/job_manager.py`

- Job objects stored in `JobManager._jobs` dictionary (key: job_id)
- Real-time progress tracking
- SSE client queues for streaming
- Thread-safe access via locks

#### 3. Database (Supabase - Optional)

**Dual-Write Pattern:** Best-effort async writes to database
**Schema:** `supabase/migrations/20250114000001_initial_schema.sql`

**Key Tables:**

**jobs**
```sql
CREATE TABLE jobs (
    job_id UUID PRIMARY KEY,
    user_id UUID,
    file_id UUID,
    filename TEXT,
    model TEXT,
    status TEXT,
    total_pages INTEGER,
    pages_completed INTEGER DEFAULT 0,
    current_stage TEXT,  -- 'ocr' or 'merge'
    progress_pct REAL DEFAULT 0.0,
    result_path TEXT,
    created_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    ...
);
```

**page_results**
```sql
CREATE TABLE page_results (
    page_result_id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES jobs(job_id),
    page_num INTEGER NOT NULL,

    -- Stage 1: OCR Results
    ocr_text TEXT,
    ocr_completed_at TIMESTAMPTZ,
    ocr_processing_time REAL,

    -- Stage 2: Merge Results
    merge_text TEXT,
    merge_completed_at TIMESTAMPTZ,
    merge_processing_time REAL,

    metadata JSONB DEFAULT '{}',
    UNIQUE(job_id, page_num)
);
```

**Database Operations:**
**Location:** `src/database/repositories/job_repository.py:173-217`

```python
async def create_page_result(
    job_id: UUID,
    page_num: int,
    ocr_text: Optional[str] = None,
    ocr_processing_time: Optional[float] = None,
    merge_text: Optional[str] = None,
    merge_processing_time: Optional[float] = None
) -> Dict[str, Any]
```

**Write Strategy:**
- Writes happen asynchronously in background threads
- Uses thread-safe `asyncio.run_coroutine_threadsafe()`
- Failures don't block main processing (best-effort)
- Each page completion triggers database write

---

## Page Tracking and Reassembly

### Tracking Mechanisms

#### 1. Intermediate Cache (IntermediateCache)

**Location:** `src/preprocessing/intermediate_cache.py`

**Cache Directory:** `{output_dir}/{job_id}.ocr_cache/`

**Operations:**
```python
cache.save_ocr_result(idx, result)      # After OCR stage
cache.load_ocr_result(idx)              # Before merge stage
cache.list_completed_pages()            # Returns [0, 1, 2, ...]
cache.clear()                           # After successful completion
```

#### 2. Checkpoint Manager (Resume Capability)

**Location:** `src/preprocessing/checkpoint_manager.py`

**Checkpoint File:** `{output_dir}/{job_id}/.checkpoint`

**Tracked Data:**
```python
checkpoint_manager.get_current_stage()       # "ocr" or "merge"
checkpoint_manager.get_stage_resume_page()   # Last completed page index
checkpoint_manager.save_stage_progress(
    stage_name="ocr|merge",
    last_completed_page=idx,
    total_pages=total,
    stage_metadata={...}
)
checkpoint_manager.complete_stage("ocr")     # Mark stage done
checkpoint_manager.clear()                   # After success
```

#### 3. Job Progress Tracking

**Location:** `src/api/services/job_manager.py:641-689`

**Updated on Progress Callback:**
```python
def update_job_progress(
    job_id: str,
    progress_pct: float,      # 0-100 (0-60 ocr, 60-90 merge)
    pages_completed: int,
    stage: str                # "ocr" or "merge"
)
```

**Progress Calculation:**
```
OCR Stage:    0-60% total progress
Merge Stage: 60-90% total progress
Final:        90-100% output writing
```

#### 4. Database Tracking

**Location:** `src/database/repositories/job_repository.py:110-139`

**Updates on Each Page Completion:**
```python
async def update_job_progress(
    job_id: UUID,
    progress_pct: float,
    pages_completed: int,
    current_stage: Optional[str] = None,
    total_pages: Optional[int] = None
)
```

### Reassembly Process

#### Method: Sequential File Append

**Location:** `src/preprocessing/staged_pipeline.py:708-731`

**Implementation:**
```python
def _write_page_result(
    output_path: Path,      # e.g., /output/{job_id}/result.markdown
    page_num: int,
    text: str,
    processing_time: float,
    method: str,           # "merge"
    append: bool           # True for pages 2+
):
    mode = 'a' if append else 'w'  # Append mode
    with open(output_path, mode) as f:
        f.write(f"<!-- Page {page_num} | Method: MERGE | Time: {time:.2f}s -->\n")
        f.write(text)
        f.write("\n\n")
        f.flush()  # Immediate disk write
```

**Characteristics:**
- Each page written immediately after merge completes
- Memory-efficient (doesn't hold all pages in RAM)
- File grows incrementally
- Frontend receives pages via SSE as they complete
- **Downside:** Frequent disk I/O (one write per page)

---

## Real-Time Streaming

### Server-Sent Events (SSE) Architecture

#### Channel 1: Job Results Stream

**Endpoint:** `GET /api/v1/process/jobs/{job_id}/stream-results`
**Location:** `src/api/processing_routes.py:340-419`

**Implementation:**
```python
async def stream_job_results():
    client_queue = asyncio.Queue()
    result_emitter = get_result_emitter()
    await result_emitter.register_client(job_id, client_queue)

    while True:
        event = await asyncio.wait_for(client_queue.get(), timeout=30.0)
        event_type = event.get("event")
        data = event.get("data")
        yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

        if event_type == "job_complete":
            break
```

**Event Types:**

**ocr_page_complete**
```json
{
  "page_num": 1,
  "text": "Extracted text content...",
  "timestamp": "2025-11-16T12:34:56.789Z"
}
```

**merge_page_complete**
```json
{
  "page_num": 1,
  "text": "Merged and refined text...",
  "timestamp": "2025-11-16T12:34:57.123Z",
  "processing_time": 1.234,
  "total_pages": 50
}
```

**stage_complete**
```json
{
  "stage": "ocr",
  "timestamp": "2025-11-16T12:35:00.000Z"
}
```

**job_complete**
```json
{
  "timestamp": "2025-11-16T12:40:00.000Z"
}
```

#### Channel 2: Batch Progress Stream

**Endpoint:** `GET /api/v1/batch/progress/stream`
**Location:** `src/api/batch_routes.py:262-332`

**Event Types:**

**document_progress**
```json
{
  "batch_job_id": "uuid",
  "job_id": "uuid",
  "filename": "document.pdf",
  "progress_pct": 45.5,
  "current_page": 23,
  "total_pages": 50,
  "stage": "merge"
}
```

**batch_progress**
```json
{
  "batch_job_id": "uuid",
  "overall_progress_pct": 67.8,
  "documents_completed": 34,
  "total_documents": 50,
  "current_document_id": "uuid",
  "current_document_progress": { ... }
}
```

**completion**
```json
{
  "batch_job_id": "uuid",
  "total_documents": 50,
  "documents_completed": 48,
  "documents_failed": 2,
  "overall_processing_time_seconds": 3600.5
}
```

### Result Emitter Implementation

**Location:** `src/api/services/result_emitter.py`

**Key Methods:**
```python
emit_ocr_page(job_id, page_num, text)           # Called after OCR
emit_merge_page(job_id, page_num, text, time)   # Called after merge
emit_stage_complete(job_id, stage)              # "ocr" or "merge"
emit_job_complete(job_id)                       # Final event
```

**Thread Safety:**
- Main event loop runs in FastAPI app thread
- Processing happens in separate worker threads
- Thread-safe emission via: `asyncio.run_coroutine_threadsafe(coro, event_loop)`
- Event loop reference set during app startup: `src/api/main.py:99`

---

## Batch Processing

### Multi-Document Processing

**Endpoint:** `POST /api/v1/batch/process`
**Location:** `src/api/services/batch_manager.py:191-335`

### Current Implementation: Sequential Processing

**Critical Finding:** Documents are processed **sequentially** (one at a time), NOT in parallel.

```python
for file_id in batch.file_ids:
    job = create_job(file_id)
    start_job(job)

    # BLOCKING: Wait for completion
    while job.status not in ['completed', 'failed', 'cancelled']:
        await asyncio.sleep(1)

    # Then process next file
```

**Implications:**
- 100-document batch = 100× single-document time
- No parallelism despite `max_concurrent_jobs = 2`
- Linear scaling only

**Configuration:** `config/settings.py`
```python
max_concurrent_jobs = 2      # Applies to separate API requests
max_concurrent_batches = 1   # Only one batch at a time
```

### Batch Output Structure

```
/tmp/ocr_api/output/{batch_job_id}/
├── {job_id_1}/
│   └── result.markdown
├── {job_id_2}/
│   └── result.markdown
└── ...
```

---

## Resume Capability

### Checkpoint System

**Location:** `src/preprocessing/checkpoint_manager.py`

**Checkpoint File Structure:**
```json
{
  "job_id": "uuid",
  "current_stage": "ocr|merge",
  "stages": {
    "ocr": {
      "status": "in_progress|completed",
      "last_completed_page": 23,
      "total_pages": 50,
      "metadata": { ... }
    },
    "merge": {
      "status": "pending|in_progress|completed",
      "last_completed_page": 10,
      "total_pages": 50,
      "metadata": { ... }
    }
  },
  "created_at": "2025-11-16T12:00:00Z",
  "updated_at": "2025-11-16T12:15:00Z"
}
```

### Resume Flow

```python
# On job start:
if checkpoint_exists:
    checkpoint = checkpoint_manager.load()
    current_stage = checkpoint.get_current_stage()  # "ocr" or "merge"
    resume_from = checkpoint.get_stage_resume_page()

    if current_stage == "ocr":
        # Resume OCR from page X
        for idx in range(resume_from + 1, total_pages):
            process_ocr_page(idx)

        # Then continue to merge stage
        complete_stage("ocr")
        for idx in range(0, total_pages):
            process_merge_page(idx)

    elif current_stage == "merge":
        # OCR complete, resume merge from page Y
        for idx in range(resume_from + 1, total_pages):
            process_merge_page(idx)
else:
    # Start fresh from OCR stage
    for idx in range(0, total_pages):
        process_ocr_page(idx)

    complete_stage("ocr")

    for idx in range(0, total_pages):
        process_merge_page(idx)
```

**Checkpoint Update Frequency:**
- Updated after **every page** completes
- Includes processing metadata (model, options, timing)
- Deleted on successful job completion
- Preserved on failure/cancellation for resume

---

## File Storage Patterns

### Upload Handler

**Location:** `src/api/services/file_manager.py:105-200+`

**Supported MIME Types:**
```python
allowed = [
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/tiff",
    "image/bmp",
    "image/gif"
]
```

**Upload Process:**
```python
async def save_upload(file: UploadFile) -> FileMetadata:
    file_id = str(uuid.uuid4())

    # Create directory
    file_dir = temp_directory / file_id
    file_dir.mkdir(parents=True, exist_ok=True)

    # Save file atomically
    storage_path = file_dir / "original"
    temp_path = storage_path.with_suffix('.tmp')

    # Write uploaded content in 1MB chunks
    with open(temp_path, "wb") as f:
        await file.seek(0)
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

    # Atomic rename
    temp_path.replace(storage_path)

    # Extract page count if PDF
    page_count = PDFHandler().count_pages(storage_path)

    return FileMetadata(
        file_id=file_id,
        filename=file.filename,
        page_count=page_count,
        storage_path=storage_path,
        expires_at=datetime.utcnow() + timedelta(hours=6)
    )
```

### Temporary File Cleanup

**Configuration:**
```python
temp_file_expiry_hours = 6  # Auto-delete after 6 hours
```

**Issue:** No automatic cleanup job implemented for:
- Failed job caches (`.ocr_cache/` directories)
- Orphaned checkpoint files
- Expired upload files

---

## Configuration

### Processing Parameters

**Location:** `config/settings.py`

```python
# Concurrency Control
max_concurrent_jobs = 2                    # Max jobs running simultaneously
max_concurrent_batches = 1                 # One batch at a time

# Model Configuration
default_model = "deepseek-ocr"
container_timeout = 300                    # 5 minutes per page

# File Management
temp_file_expiry_hours = 6
api_temp_directory = "/tmp/ocr_api/uploads"
api_processing_directory = "/tmp/ocr_api/processing"
api_output_directory = "/tmp/ocr_api/output"

# Processing Options
prefer_quality = True                      # Quality vs speed tradeoff
enable_memory_profiling = False
enable_system_monitoring = True
```

### Per-Request Options

**Processing Options:**
```python
{
  "dpi": 300,                              # 72-600, default 300
  "method": "auto|extract|ocr|hybrid",
  "start_page": 1,                         # 1-indexed, optional
  "end_page": 50,                          # 1-indexed, optional
  "staged_pipeline": true,                 # Always true
  "prefer_quality": true
}
```

---

## Critical File References

### API Layer
- **Main Application:** `src/api/main.py`
- **Processing Routes:** `src/api/processing_routes.py`
- **Batch Routes:** `src/api/batch_routes.py`

### Service Layer
- **Job Manager:** `src/api/services/job_manager.py`
- **Batch Manager:** `src/api/services/batch_manager.py:191-335`
- **File Manager:** `src/api/services/file_manager.py`
- **Result Emitter:** `src/api/services/result_emitter.py`
- **Progress Emitter:** `src/api/services/progress_emitter.py`

### Processing Layer
- **Staged Pipeline:** `src/preprocessing/staged_pipeline.py:332-731`
- **Intermediate Cache:** `src/preprocessing/intermediate_cache.py`
- **Checkpoint Manager:** `src/preprocessing/checkpoint_manager.py`
- **PDF Handler:** `src/preprocessing/pdf_handler.py`

### Database Layer
- **Schema:** `supabase/migrations/20250114000001_initial_schema.sql`
- **Job Repository:** `src/database/repositories/job_repository.py:110-217`
- **File Repository:** `src/database/repositories/file_repository.py`

### Configuration
- **Settings:** `config/settings.py`

---

## Architecture Analysis

### Strengths ✅

| Aspect | Strength |
|--------|----------|
| **Pipeline Design** | Clean separation of OCR and merge stages |
| **Resume Capability** | Robust checkpoint system for failure recovery |
| **Real-Time Updates** | SSE streaming provides live progress updates |
| **Memory Efficiency** | Append-based output prevents holding full documents in RAM |
| **Database Resilience** | Dual-write pattern (filesystem + database) |
| **Error Handling** | Per-page error isolation with checkpoint recovery |

### Weaknesses ❌

| Aspect | Issue | Impact |
|--------|-------|--------|
| **Batch Processing** | Sequential document processing | 2x slower than possible |
| **Page Batching** | No page-level batching | 3-5x slower per document |
| **Disk I/O** | Per-page writes (output, cache, checkpoint, DB) | 50-100+ writes per job |
| **Parallelism** | Single-threaded page processing | Cannot leverage multi-core CPUs |
| **Cache Cleanup** | No automatic cleanup of failed job artifacts | Disk space leaks |
| **Database Writes** | Per-page database inserts | Excessive DB transactions |

### Performance Bottlenecks

**For a 100-page document:**
```
Current Architecture:
  OCR Stage:   100 pages × 1-2 seconds = 100-200 seconds
  Merge Stage: 100 pages × 1-2 seconds = 100-200 seconds
  Disk I/O:    100 writes × 3 locations = 300 disk operations
  DB Writes:   100 page_results inserts
  Total Time:  200-400 seconds (3-7 minutes)

Potential with Optimizations:
  OCR Stage:   25 batches × 2 seconds = 50 seconds (4x faster)
  Merge Stage: 25 batches × 2 seconds = 50 seconds (4x faster)
  Disk I/O:    10 buffered writes = 30 disk operations (10x reduction)
  DB Writes:   10 bulk inserts
  Total Time:  100-120 seconds (1.5-2 minutes) = 3-4x speedup
```

---

## Recommendations

### 🔴 HIGH PRIORITY - Critical Architecture Issues

#### 1. Batch Processing Inefficiency

**Problem:**
- Batch documents processed **sequentially** (one at a time)
- With `max_concurrent_jobs = 2`, could run 2 jobs simultaneously
- Batch processing doesn't leverage this capability
- 100-document batch = 16-33 hours at 1-2 min/page

**Location:** `src/api/services/batch_manager.py:191-335`

**Recommendation:**
```python
# Replace sequential processing with concurrent pool
import asyncio
from asyncio import Semaphore

async def process_batch_concurrent(batch: BatchJob):
    semaphore = Semaphore(max_concurrent_jobs)  # Limit to 2

    async def process_with_limit(file_id):
        async with semaphore:
            job = create_job(file_id)
            await start_job(job)
            return await wait_for_completion(job)

    # Process all files concurrently (limited by semaphore)
    results = await asyncio.gather(*[
        process_with_limit(fid) for fid in batch.file_ids
    ], return_exceptions=True)

    return results
```

**Impact:** 50% time reduction for batches (2x parallelism)
**Effort:** Medium
**ROI:** ⭐⭐⭐⭐⭐

---

#### 2. Page-Level Processing Bottleneck

**Problem:**
- Pages processed one at a time within each document
- No batching of pages to containers
- Container startup/teardown overhead per page
- Total time = (OCR_time + merge_time) × num_pages

**Location:** `src/preprocessing/staged_pipeline.py:332-706`

**Recommendation A: Mini-Batch Inference**
```python
# Process pages in batches of 4-8
BATCH_SIZE = 4

for batch_start in range(0, total_pages, BATCH_SIZE):
    batch_end = min(batch_start + BATCH_SIZE, total_pages)
    batch_pages = pages_data[batch_start:batch_end]

    # Send batch to container
    batch_results = model_manager.infer_batch(
        model="deepseek-ocr",
        images=[p[1] for p in batch_pages]
    )

    # Cache all results
    for idx, result in enumerate(batch_results):
        cache.save_ocr_result(batch_start + idx, result)
        emit_progress(...)
```

**Impact:** 2-4x speedup (amortize container overhead)
**Effort:** High (requires container API changes)
**ROI:** ⭐⭐⭐⭐⭐

**Recommendation B: Parallel Page Processing**
```python
# Process pages in parallel (limited concurrency)
from concurrent.futures import ThreadPoolExecutor

def process_page_ocr(page_idx):
    image = pages_data[page_idx][1]
    result = model_manager.infer(model="deepseek-ocr", image=image)
    cache.save_ocr_result(page_idx, result)
    return result

with ThreadPoolExecutor(max_workers=4) as executor:
    futures = [
        executor.submit(process_page_ocr, idx)
        for idx in range(start_page, total_pages)
    ]

    # Collect results as they complete
    for future in concurrent.futures.as_completed(futures):
        result = future.result()
        emit_progress(...)
```

**Impact:** 3-5x speedup (parallel container inference)
**Effort:** High (requires thread-safe container management)
**ROI:** ⭐⭐⭐⭐⭐

---

#### 3. Memory Inefficiency in Final Output

**Problem:**
- Final output file written via **append mode** with `f.flush()` after every page
- Frequent disk I/O (50-100+ disk writes for large documents)
- No compression or streaming to cloud storage

**Location:** `src/preprocessing/staged_pipeline.py:708-731`

**Recommendation:**
```python
# Option 1: Buffer writes
output_buffer = []
BUFFER_SIZE = 10  # Pages

for page_idx in range(start_page, total_pages):
    merged_text = merge_page(page_idx)
    output_buffer.append(merged_text)

    # Emit SSE immediately
    emit_merge_page(job_id, page_idx + 1, merged_text)

    # Flush every 10 pages
    if len(output_buffer) >= BUFFER_SIZE:
        with open(output_path, 'a') as f:
            f.write('\n\n'.join(output_buffer))
        output_buffer.clear()

# Flush remaining
if output_buffer:
    with open(output_path, 'a') as f:
        f.write('\n\n'.join(output_buffer))

# Option 2: Stream directly to S3 (if using cloud storage)
import aioboto3

async def stream_to_s3():
    async with aioboto3.client('s3') as s3:
        await s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=output_stream
        )
```

**Impact:** 10-20x fewer disk operations, better cloud integration
**Effort:** Low
**ROI:** ⭐⭐⭐⭐

---

### 🟡 MEDIUM PRIORITY - Scalability & Robustness

#### 4. Database Write Inefficiency

**Problem:**
- Database writes happen **per-page** during processing
- Dual-write pattern increases latency (even if async)
- No batching of database inserts
- 100 pages = 100 database transactions

**Location:** `src/database/repositories/job_repository.py:173-217`

**Recommendation:**
```python
# Batch database writes
page_results_batch = []
BATCH_SIZE = 10

for page_idx in range(start_page, total_pages):
    result = process_page(page_idx)

    page_results_batch.append({
        'job_id': job_id,
        'page_num': page_idx + 1,
        'merge_text': result.text,
        'merge_processing_time': result.time
    })

    # Flush batch every 10 pages
    if len(page_results_batch) >= BATCH_SIZE:
        await job_repository.bulk_create_page_results(page_results_batch)
        page_results_batch.clear()

# Flush remaining
if page_results_batch:
    await job_repository.bulk_create_page_results(page_results_batch)
```

**Add to repository:**
```python
async def bulk_create_page_results(self, results: List[Dict]) -> None:
    """Bulk insert page results"""
    await self.supabase.table('page_results').insert(results).execute()
```

**Impact:** 10x fewer database transactions, reduced latency
**Effort:** Low
**ROI:** ⭐⭐⭐⭐

---

#### 5. Checkpoint Granularity

**Problem:**
- Checkpoints saved **after every page**
- Disk I/O overhead for large documents
- 100 pages = 100 checkpoint writes

**Location:** `src/preprocessing/checkpoint_manager.py`

**Recommendation:**
```python
# Save checkpoints every N pages or every M seconds
CHECKPOINT_PAGE_INTERVAL = 5
CHECKPOINT_TIME_INTERVAL = 30  # seconds

last_checkpoint_time = time.time()

for page_idx in range(start_page, total_pages):
    process_page(page_idx)

    # Checkpoint every 5 pages OR 30 seconds
    if (page_idx % CHECKPOINT_PAGE_INTERVAL == 0 or
        time.time() - last_checkpoint_time > CHECKPOINT_TIME_INTERVAL):
        checkpoint_manager.save_stage_progress("merge", page_idx)
        last_checkpoint_time = time.time()

# Final checkpoint
checkpoint_manager.save_stage_progress("merge", total_pages - 1)
```

**Impact:** 5-10x fewer checkpoint writes
**Effort:** Low
**ROI:** ⭐⭐⭐

---

#### 6. Intermediate Cache Cleanup

**Problem:**
- OCR cache persists in `.ocr_cache/` directory
- Only cleaned up on **successful completion**
- Failed jobs leave orphaned cache files
- No automatic cleanup of expired files

**Location:** `src/preprocessing/intermediate_cache.py`

**Recommendation:**
```python
# Add cleanup to finally block
try:
    # Process stages...
    result = process_document()
finally:
    # Always cleanup intermediate cache (success or failure)
    try:
        cache.clear()
    except Exception as e:
        logger.warning(f"Failed to cleanup cache: {e}")

    # Only cleanup checkpoint on success
    if job.status == "completed":
        checkpoint_manager.clear()

# Add scheduled cleanup job in main.py
@app.on_event("startup")
async def start_background_tasks():
    asyncio.create_task(periodic_cache_cleanup())

async def periodic_cache_cleanup():
    """Cleanup expired caches and uploads every hour"""
    while True:
        await asyncio.sleep(3600)  # Every hour
        try:
            cleanup_caches_older_than(hours=6)
            cleanup_uploads_older_than(hours=6)
        except Exception as e:
            logger.error(f"Cache cleanup failed: {e}")
```

**Impact:** Prevent disk space leaks from failed jobs
**Effort:** Low
**ROI:** ⭐⭐⭐

---

### 🟢 LOW PRIORITY - Nice-to-Have Enhancements

#### 7. Progress Granularity

**Problem:**
- Progress reported per-page (good)
- But large pages may appear "stuck" for 30-60 seconds
- No sub-page progress indication

**Recommendation:**
```python
# Add sub-page progress for long-running operations
def progress_callback_with_substeps(page_idx, substep):
    # substep: "extracting" | "inferring" | "merging" | "writing"
    page_progress = (page_idx / total_pages) * 100
    substep_map = {
        "extracting": 0,    # 0% of page
        "inferring": 50,    # 50% of page
        "merging": 75,      # 75% of page
        "writing": 90       # 90% of page
    }

    page_sub_pct = substep_map.get(substep, 0)
    overall_pct = page_progress + (page_sub_pct / total_pages)

    emit_progress(overall_pct, substep=substep)

# Usage in pipeline
for page_idx in range(total_pages):
    progress_callback(page_idx, "extracting")
    image = extract_page(page_idx)

    progress_callback(page_idx, "inferring")
    ocr_result = model_infer(image)

    progress_callback(page_idx, "merging")
    merged = merge_texts(ocr_result, embedded_text)

    progress_callback(page_idx, "writing")
    write_output(merged)
```

**Impact:** Better UX for users
**Effort:** Medium
**ROI:** ⭐⭐

---

#### 8. Adaptive Batching

**Problem:**
- Fixed sequential processing regardless of document size
- Small documents (1-2 pages) waste overhead
- No intelligence in batch strategy

**Recommendation:**
```python
# Smart batching based on document size
def determine_batch_strategy(files: List[FileMetadata]):
    total_pages = sum(f.page_count for f in files)
    avg_pages = total_pages / len(files)

    if avg_pages < 5:
        # Small docs: aggressive parallelism
        return ParallelBatchStrategy(max_workers=4)
    elif avg_pages < 20:
        # Medium docs: moderate parallelism
        return ParallelBatchStrategy(max_workers=2)
    else:
        # Large docs: sequential with page-level parallelism
        return SequentialBatchStrategy(page_parallelism=True)

# Apply strategy
strategy = determine_batch_strategy(batch.files)
results = await strategy.execute(batch)
```

**Impact:** Smarter resource utilization
**Effort:** High
**ROI:** ⭐⭐

---

#### 9. Result Compression

**Problem:**
- Large text outputs stored uncompressed
- 100-page document = 500KB-5MB text file
- Wastes storage and bandwidth

**Recommendation:**
```python
# Compress final output
import gzip

# Write compressed version alongside raw
with gzip.open(f"{output_path}.gz", 'wt', encoding='utf-8') as f:
    f.write(final_text)

# Store both paths (or just compressed)
job.result_path = str(output_path)
job.compressed_result_path = f"{output_path}.gz"

# Serve compressed version with Content-Encoding header
@app.get("/api/v1/process/jobs/{job_id}/result")
async def get_result(
    job_id: str,
    accept_encoding: Optional[str] = Header(None)
):
    job = job_manager.get_job(job_id)

    if "gzip" in (accept_encoding or "") and job.compressed_result_path:
        return FileResponse(
            job.compressed_result_path,
            headers={"Content-Encoding": "gzip"}
        )
    else:
        return FileResponse(job.result_path)
```

**Impact:** 60-80% storage reduction
**Effort:** Low
**ROI:** ⭐⭐

---

## Summary

### Recommendations Priority Matrix

| Priority | Issue | Impact | Effort | ROI | Recommended? |
|----------|-------|--------|--------|-----|--------------|
| 🔴 HIGH | Batch sequential processing | 2x speedup | Medium | ⭐⭐⭐⭐⭐ | **YES** |
| 🔴 HIGH | Page-level batching/parallel | 3-5x speedup | High | ⭐⭐⭐⭐⭐ | **YES** |
| 🔴 HIGH | Output append buffering | 10x fewer I/O | Low | ⭐⭐⭐⭐ | **YES** |
| 🟡 MED | DB write batching | 10x fewer txns | Low | ⭐⭐⭐⭐ | **YES** |
| 🟡 MED | Checkpoint granularity | 5x fewer writes | Low | ⭐⭐⭐ | **YES** |
| 🟡 MED | Cache cleanup | Prevent leaks | Low | ⭐⭐⭐ | **YES** |
| 🟢 LOW | Progress granularity | Better UX | Medium | ⭐⭐ | Optional |
| 🟢 LOW | Adaptive batching | Smarter scaling | High | ⭐⭐ | Optional |
| 🟢 LOW | Result compression | 70% storage | Low | ⭐⭐ | Optional |

### Quick Wins (Low Effort, High Impact)

1. **Output Buffering** → 10x fewer disk operations
2. **Database Write Batching** → 10x fewer transactions
3. **Checkpoint Granularity** → 5x fewer checkpoint writes
4. **Cache Cleanup** → Prevent disk space leaks

### Major Performance Gains (High Effort, High Impact)

1. **Page-Level Parallelism** → 3-5x speedup per document
2. **Concurrent Batch Processing** → 2x batch throughput

---

**Next Steps:**
1. Test current multi-page flow to establish baseline metrics
2. Implement quick wins first (recommendations #3, #4, #5, #6)
3. Design and implement page-level parallelism (recommendation #2)
4. Design and implement concurrent batch processing (recommendation #1)
5. Re-test and measure performance improvements

---

**Document End**
