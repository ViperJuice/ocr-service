# Supabase Migration Specification

**Project:** OCR Service with DeepSeek-OCR and Qwen3-VL
**Architecture:** CQRS/Event-Driven with Supabase Backend
**Date:** 2025-01-14
**Status:** Planning Phase

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Architecture Overview](#architecture-overview)
3. [Database Schema Design](#database-schema-design)
4. [Implementation Phases](#implementation-phases)
5. [File Changes Specification](#file-changes-specification)
6. [API Changes](#api-changes)
7. [Frontend Changes](#frontend-changes)
8. [Deployment Architecture](#deployment-architecture)
9. [Testing Strategy](#testing-strategy)
10. [Migration Checklist](#migration-checklist)

---

## Executive Summary

### Current State
- **In-memory job state** - All jobs stored in Python dictionaries, lost on restart
- **Local filesystem storage** - Files stored in `data/temp/` with expiry
- **SSE for real-time** - Server-Sent Events with manual connection management
- **No persistence** - No job history or audit trail
- **Single instance only** - Cannot scale horizontally

### Target State
- **Database-backed state** - All jobs persisted in Supabase PostgreSQL
- **Supabase Storage** - Files stored in cloud storage buckets
- **Supabase Realtime** - WebSocket-based real-time subscriptions
- **Full audit trail** - Event sourcing with `job_events` table
- **Multi-instance ready** - Shared state enables horizontal scaling
- **Multi-user support** - User authentication with API keys

### Migration Strategy
**Incremental, non-breaking migration in 5 phases:**
1. **Setup** - Supabase local, schema, repositories
2. **Dual-write** - Write to both memory AND database
3. **Dual-subscribe** - Frontend uses both SSE AND Realtime
4. **Remove SSE** - Validate and remove old infrastructure
5. **Database-only** - Remove in-memory state entirely

### Key Benefits
- ✅ Jobs survive restarts
- ✅ Full job history and analytics
- ✅ Real-time updates with automatic reconnection
- ✅ Multi-user support from day one
- ✅ Job versioning (re-process with different prompts)
- ✅ Horizontal scalability
- ✅ Seamless local → cloud deployment

---

## Architecture Overview

### Current Architecture (In-Memory)

```mermaid
graph TB
    subgraph Local["Local Machine"]
        subgraph Frontend["Next.js Frontend"]
            UI[Next.js UI]
        end

        subgraph Backend["FastAPI Backend"]
            JobMgr["JobManager<br/>(Dict)<br/>- jobs: Dict[str, Job]<br/>- In-memory only<br/>- Lost on restart"]
            FileMgr["FileManager<br/>(Filesystem)<br/>- data/temp/<br/>- metadata.json per file"]
        end

        subgraph GPU["GPU Containers"]
            DeepSeek["DeepSeek Container<br/>GPU 0 - RTX 4090<br/>Port 8001"]
            Qwen["Qwen3-VL Container<br/>GPU 1 - RTX 4090<br/>Port 8002"]
        end

        UI <-->|SSE| Backend
        UI <-->|Polling| Backend
        Backend <-->|HTTP| DeepSeek
        Backend <-->|HTTP| Qwen
    end

    style JobMgr fill:#ffcccc
    style FileMgr fill:#ffcccc
    style UI fill:#cce5ff
    style Backend fill:#ffe5cc
    style GPU fill:#e5ffcc
```

### Target Architecture (Supabase-Backed)

```mermaid
graph TB
    subgraph Local["Local Development"]
        subgraph Frontend["Next.js Frontend"]
            UI["Next.js UI<br/>Supabase JS<br/>- Realtime subs<br/>- Auto-reconnect"]
        end

        subgraph Backend["FastAPI Backend"]
            JobMgr["JobManager<br/>(Repository)<br/>- job_repository.get_job()<br/>- No in-memory state<br/>- Reads from database"]
            FileMgr["FileManager<br/>(Supabase Storage)<br/>- Upload to storage bucket<br/>- Metadata in database"]
        end

        subgraph GPU["GPU Containers"]
            DeepSeek["DeepSeek Container<br/>GPU 0 - RTX 4090<br/>Port 8001"]
            Qwen["Qwen3-VL Container<br/>GPU 1 - RTX 4090<br/>Port 8002"]
        end

        subgraph Supabase["Supabase Local (Docker)"]
            DB["PostgreSQL Database<br/>Port 54322<br/>├─ jobs table<br/>├─ files table<br/>├─ page_results table<br/>├─ job_events table<br/>├─ batch_jobs table<br/>├─ directories table<br/>└─ users table"]
            RT["Realtime Server<br/>WebSocket - Port 54321<br/>Broadcasts database changes"]
            Storage["Storage Buckets<br/>├─ ocr-uploads<br/>└─ ocr-results"]
        end

        UI <-->|WebSocket| RT
        DB --|Read|--> UI
        Backend <-->|Read/Write| DB
        Backend <-->|Upload/Download| Storage
        Backend <-->|HTTP| DeepSeek
        Backend <-->|HTTP| Qwen
    end

    style JobMgr fill:#ccffcc
    style FileMgr fill:#ccffcc
    style DB fill:#cce5ff
    style RT fill:#e5ccff
    style Storage fill:#ffffcc
```

### Cloud Deployment Architecture (Future - Phase 6)

```mermaid
graph TB
    Internet((Internet))

    subgraph Vercel["Vercel (Frontend)"]
        NextJS["Next.js App<br/>Realtime WebSocket"]
    end

    subgraph Railway["Railway (Backend)"]
        FastAPI["FastAPI API<br/>- JobManager<br/>- Repositories"]
    end

    subgraph Supabase["Supabase Cloud"]
        SBDB["PostgreSQL"]
        SBRT["Realtime Server"]
        SBStorage["Storage Buckets"]
        SBRLS["Row Level Security"]
    end

    subgraph Hetzner["Hetzner GEX44 GPU Server"]
        GPU1["DeepSeek Container"]
        GPU2["Qwen3-VL Container"]
        NVIDIA["NVIDIA RTX 4000 Ada (20GB)"]
    end

    Internet <--> NextJS
    NextJS <-->|HTTPS/WSS| SBRT
    NextJS <-->|HTTPS| FastAPI
    FastAPI <-->|SQL| SBDB
    FastAPI <-->|HTTPS/VPN/Tailscale| GPU1
    FastAPI <-->|HTTPS/VPN/Tailscale| GPU2
    GPU1 -.->|Uses| NVIDIA
    GPU2 -.->|Uses| NVIDIA

    style Vercel fill:#000,stroke:#fff,color:#fff
    style Railway fill:#7c3aed,stroke:#fff,color:#fff
    style Supabase fill:#3ecf8e,stroke:#fff,color:#000
    style Hetzner fill:#d50c2d,stroke:#fff,color:#fff
```

**Deployment Decision Deferred:** Local development first, cloud deployment in Phase 6.
**Recommended Option:** Railway (backend) + Hetzner GEX44 (GPU) + Vercel (frontend) (~$225/month)

---

## Database Schema Design

### Schema Principles
- **User-scoped data** - All tables have `user_id` foreign key
- **Soft deletes** - Use `deleted_at` timestamp instead of hard deletes
- **JSONB for flexibility** - `custom_prompts`, `processing_options`, `metadata`
- **Timestamps** - `created_at`, `started_at`, `completed_at` for all jobs
- **Event sourcing** - `job_events` table provides full audit trail
- **Row Level Security** - Enabled on all tables (users only see their data)
- **Realtime enabled** - `jobs`, `page_results`, `job_events`, `batch_jobs` published

### Entity Relationship Diagram

```mermaid
erDiagram
    users ||--o{ files : "uploads"
    users ||--o{ jobs : "creates"
    users ||--o{ directories : "creates"
    users ||--o{ batch_jobs : "creates"

    files ||--o{ jobs : "processes"
    files }o--|| directory_files : "belongs to"

    directories ||--o{ directory_files : "contains"

    jobs ||--o{ page_results : "has"
    jobs ||--o{ job_events : "logs"
    jobs }o--o| jobs : "versions (parent_job_id)"
    jobs }o--|| batch_jobs : "belongs to"

    users {
        uuid user_id PK
        text email UK
        text api_key UK
        timestamptz created_at
        boolean is_active
    }

    files {
        uuid file_id PK
        uuid user_id FK
        text filename
        text content_type
        bigint size_bytes
        integer page_count
        text storage_bucket
        text storage_path
        timestamptz uploaded_at
        timestamptz expires_at
        timestamptz deleted_at
        jsonb metadata
    }

    jobs {
        uuid job_id PK
        uuid user_id FK
        uuid file_id FK
        text filename
        text model
        text prompt_type
        jsonb custom_prompts
        jsonb processing_options
        text output_format
        text status
        timestamptz created_at
        timestamptz started_at
        timestamptz completed_at
        integer total_pages
        integer pages_completed
        text current_stage
        real progress_pct
        text result_path
        text error_message
        uuid parent_job_id FK
        integer version_number
        uuid parent_batch_id FK
        jsonb metadata
    }

    page_results {
        uuid page_result_id PK
        uuid job_id FK
        integer page_num
        text ocr_text
        timestamptz ocr_completed_at
        real ocr_processing_time
        text merge_text
        timestamptz merge_completed_at
        real merge_processing_time
        jsonb metadata
    }

    job_events {
        bigserial event_id PK
        uuid job_id FK
        text event_type
        jsonb event_data
        timestamptz created_at
    }

    batch_jobs {
        uuid batch_job_id PK
        uuid user_id FK
        text name
        text status
        integer total_documents
        integer documents_completed
        real overall_progress_pct
        timestamptz created_at
        timestamptz started_at
        timestamptz completed_at
        text model
        text prompt_type
        jsonb custom_prompts
        jsonb processing_options
        text output_format
        text error_message
        jsonb metadata
    }

    directories {
        uuid directory_id PK
        uuid user_id FK
        text name
        bigint total_size
        timestamptz uploaded_at
    }

    directory_files {
        uuid directory_id FK
        uuid file_id FK
        integer sequence_num
    }
```

### Table Definitions

#### `users` - User Authentication

```sql
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email TEXT UNIQUE NOT NULL,
    api_key TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Indexes
CREATE INDEX idx_users_api_key ON users(api_key);
CREATE INDEX idx_users_email ON users(email);

-- Row Level Security
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own data" ON users
    FOR SELECT USING (auth.uid() = user_id);
```

**Purpose:** Store user credentials for multi-user support
**Auth Method:** API key-based (simple), can upgrade to JWT later
**Test User:** Created in seed data with `dev_test_key_12345`

---

#### `files` - File Metadata

```sql
CREATE TABLE files (
    file_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,

    -- File information
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    page_count INTEGER,

    -- Storage reference (Supabase Storage)
    storage_bucket TEXT DEFAULT 'ocr-uploads',
    storage_path TEXT NOT NULL,

    -- Lifecycle management
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,

    -- Extensibility
    metadata JSONB DEFAULT '{}'
);

-- Indexes
CREATE INDEX idx_files_user_id ON files(user_id);
CREATE INDEX idx_files_expires_at ON files(expires_at) WHERE deleted_at IS NULL;
CREATE INDEX idx_files_storage_path ON files(storage_path);

-- Row Level Security
ALTER TABLE files ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can access own files" ON files
    FOR ALL USING (user_id = current_setting('app.user_id')::uuid);
```

**Purpose:** Store file metadata separately from file content
**Storage:** File content in Supabase Storage bucket, metadata in table
**Expiry:** `expires_at` enables automatic cleanup (6 hours default)
**Soft Delete:** `deleted_at` allows recovery before permanent deletion

---

#### `jobs` - OCR Processing Jobs

```sql
CREATE TABLE jobs (
    job_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    file_id UUID NOT NULL REFERENCES files(file_id) ON DELETE CASCADE,

    -- Job configuration
    filename TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT 'deepseek-ocr',
    prompt_type TEXT DEFAULT 'markdown',
    custom_prompts JSONB,
    processing_options JSONB DEFAULT '{}',
    output_format TEXT DEFAULT 'markdown',

    -- Status and progress
    status TEXT NOT NULL CHECK (status IN ('queued', 'processing', 'completed', 'failed', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    total_pages INTEGER,
    pages_completed INTEGER DEFAULT 0,
    current_stage TEXT,  -- 'ocr' or 'merge'
    progress_pct REAL DEFAULT 0.0,

    -- Results and errors
    result_path TEXT,  -- Path to final markdown file
    error_message TEXT,

    -- Job versioning (re-processing same document with different prompts)
    parent_job_id UUID REFERENCES jobs(job_id) ON DELETE SET NULL,
    version_number INTEGER DEFAULT 1,

    -- Batch relationship
    parent_batch_id UUID,  -- FK added after batch_jobs table created

    -- Extensibility
    metadata JSONB DEFAULT '{}'
);

-- Indexes
CREATE INDEX idx_jobs_user_id ON jobs(user_id);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_created_at ON jobs(created_at DESC);
CREATE INDEX idx_jobs_file_id ON jobs(file_id);
CREATE INDEX idx_jobs_parent_job ON jobs(parent_job_id);
CREATE INDEX idx_jobs_parent_batch ON jobs(parent_batch_id);

-- Row Level Security
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can access own jobs" ON jobs
    FOR ALL USING (user_id = current_setting('app.user_id')::uuid);

-- Enable Realtime
ALTER PUBLICATION supabase_realtime ADD TABLE jobs;
```

**Purpose:** Store OCR job state and configuration
**Status Enum:** queued → processing → completed/failed/cancelled
**Versioning:** `parent_job_id` + `version_number` enable re-processing with different prompts
**Progress Tracking:** `pages_completed`, `progress_pct`, `current_stage` for real-time UI
**Realtime:** Frontend subscribes to job updates via WebSocket

---

#### `page_results` - Per-Page OCR Results

```sql
CREATE TABLE page_results (
    page_result_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    page_num INTEGER NOT NULL,

    -- OCR stage results
    ocr_text TEXT,
    ocr_completed_at TIMESTAMPTZ,
    ocr_processing_time REAL,

    -- Merge stage results
    merge_text TEXT,
    merge_completed_at TIMESTAMPTZ,
    merge_processing_time REAL,

    -- Extensibility
    metadata JSONB DEFAULT '{}',

    UNIQUE(job_id, page_num)
);

-- Indexes
CREATE INDEX idx_page_results_job_id ON page_results(job_id, page_num);

-- Row Level Security
ALTER TABLE page_results ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can access own page results" ON page_results
    FOR ALL USING (job_id IN (SELECT job_id FROM jobs WHERE user_id = current_setting('app.user_id')::uuid));

-- Enable Realtime
ALTER PUBLICATION supabase_realtime ADD TABLE page_results;
```

**Purpose:** Store granular per-page results for progressive rendering
**Two-Stage:** OCR stage (raw extraction) → Merge stage (refinement)
**Upsert Pattern:** Backend calls `upsert()` to update OCR then Merge text
**Realtime:** Frontend subscribes to see pages appear as they complete

---

#### `job_events` - Audit Log (Event Sourcing)

```sql
CREATE TABLE job_events (
    event_id BIGSERIAL PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    event_data JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_job_events_job_id ON job_events(job_id, created_at);
CREATE INDEX idx_job_events_type ON job_events(event_type);
CREATE INDEX idx_job_events_created_at ON job_events(created_at DESC);

-- Row Level Security
ALTER TABLE job_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can access own job events" ON job_events
    FOR ALL USING (job_id IN (SELECT job_id FROM jobs WHERE user_id = current_setting('app.user_id')::uuid));

-- Enable Realtime
ALTER PUBLICATION supabase_realtime ADD TABLE job_events;
```

**Purpose:** Immutable audit log of all job lifecycle events
**Event Types:**
- `job_created`, `job_queued`, `job_started`, `job_cancelled`
- `ocr_page_started`, `ocr_page_completed`, `ocr_stage_completed`
- `merge_page_started`, `merge_page_completed`, `merge_stage_completed`
- `job_completed`, `job_failed`
- `model_loaded`, `model_unloaded` (future)

**Event Sourcing Lite:** `jobs` table is source of truth, events are audit trail
**Use Cases:** Debugging, analytics, rebuilding timeline, compliance

---

#### `batch_jobs` - Batch Processing

```sql
CREATE TABLE batch_jobs (
    batch_job_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,

    name TEXT,
    status TEXT NOT NULL CHECK (status IN ('queued', 'processing', 'completed', 'failed', 'cancelled')),

    total_documents INTEGER NOT NULL,
    documents_completed INTEGER DEFAULT 0,
    overall_progress_pct REAL DEFAULT 0.0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    -- Configuration (inherited by child jobs)
    model TEXT NOT NULL DEFAULT 'deepseek-ocr',
    prompt_type TEXT DEFAULT 'markdown',
    custom_prompts JSONB,
    processing_options JSONB DEFAULT '{}',
    output_format TEXT DEFAULT 'markdown',

    -- Error tracking
    error_message TEXT,

    -- Extensibility
    metadata JSONB DEFAULT '{}'
);

-- Indexes
CREATE INDEX idx_batch_jobs_user_id ON batch_jobs(user_id);
CREATE INDEX idx_batch_jobs_status ON batch_jobs(status);
CREATE INDEX idx_batch_jobs_created_at ON batch_jobs(created_at DESC);

-- Row Level Security
ALTER TABLE batch_jobs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can access own batch jobs" ON batch_jobs
    FOR ALL USING (user_id = current_setting('app.user_id')::uuid);

-- Enable Realtime
ALTER PUBLICATION supabase_realtime ADD TABLE batch_jobs;

-- Add FK constraint to jobs table (after batch_jobs exists)
ALTER TABLE jobs ADD CONSTRAINT fk_jobs_batch
    FOREIGN KEY (parent_batch_id) REFERENCES batch_jobs(batch_job_id) ON DELETE CASCADE;
```

**Purpose:** Group multiple document processing jobs
**Relationship:** Batch → Jobs (one-to-many via `parent_batch_id`)
**Use Cases:**
- Multiple PDF files uploaded at once
- Multiple image pages treated as single document (batch of 1 job with N pages)

---

#### `directories` - Multi-File Upload Groups

```sql
CREATE TABLE directories (
    directory_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    total_size BIGINT NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_directories_user_id ON directories(user_id);

-- Row Level Security
ALTER TABLE directories ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can access own directories" ON directories
    FOR ALL USING (user_id = current_setting('app.user_id')::uuid);
```

**Purpose:** Track multi-file uploads (for batch processing)

---

#### `directory_files` - Junction Table

```sql
CREATE TABLE directory_files (
    directory_id UUID NOT NULL REFERENCES directories(directory_id) ON DELETE CASCADE,
    file_id UUID NOT NULL REFERENCES files(file_id) ON DELETE CASCADE,
    sequence_num INTEGER NOT NULL,

    PRIMARY KEY (directory_id, file_id),
    UNIQUE (directory_id, sequence_num)
);

-- Indexes
CREATE INDEX idx_directory_files_directory ON directory_files(directory_id, sequence_num);
```

**Purpose:** Many-to-many relationship between directories and files with ordering

---

### Storage Buckets

#### `ocr-uploads` - Uploaded Files

```javascript
// Supabase Storage bucket config
{
  name: "ocr-uploads",
  public: false,  // Require authentication
  allowedMimeTypes: [
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/tiff"
  ],
  fileSizeLimit: 52428800,  // 50 MB
  avifAutoDetection: false
}
```

**Structure:**
```
ocr-uploads/
  └── {user_id}/
      └── {file_id}/
          └── {original_filename}
```

---

#### `ocr-results` - Final Output Files

```javascript
{
  name: "ocr-results",
  public: false,
  allowedMimeTypes: [
    "text/markdown",
    "application/json",
    "text/plain"
  ],
  fileSizeLimit: 10485760  // 10 MB
}
```

**Structure:**
```
ocr-results/
  └── {user_id}/
      └── {job_id}/
          └── {job_id}.{format}  // e.g., abc-123.markdown
```

---

## Implementation Phases

### Phase 1: Supabase Local Setup & Database Schema

**Goal:** Set up local Supabase instance, create database schema, initialize repositories.

**Duration:** 2-3 hours

**Prerequisites:**
- Supabase CLI installed
- Docker running (for Supabase local)
- Python environment ready

```mermaid
graph LR
    A[Install Supabase CLI] --> B[supabase init]
    B --> C[supabase start]
    C --> D[Create Migration]
    D --> E[Create .env]
    E --> F[supabase db reset]
    F --> G[Verify in Studio]
    G --> H[Create Storage Buckets]
    H --> I[Install Python Deps]
    I --> J[Create Repositories]
    J --> K[Write Tests]
    K --> L[Commit Phase 1]

    style L fill:#90EE90
```

**Steps:**

1. **Install Supabase CLI**
   ```bash
   # macOS
   brew install supabase/tap/supabase

   # Or via npm (cross-platform)
   npm install -g supabase
   ```

2. **Initialize Supabase Project**
   ```bash
   cd /home/jenner/code/ocr-service
   supabase init
   ```

   This creates:
   - `supabase/` directory
   - `supabase/config.toml` - Configuration
   - `supabase/migrations/` - SQL migrations

3. **Start Supabase Local Stack**
   ```bash
   supabase start
   ```

   This starts Docker containers:
   - PostgreSQL (port 54322)
   - PostgREST API (port 54321)
   - Realtime Server (WebSocket)
   - Studio UI (port 54323)
   - Storage API

   **Output will include:**
   ```
   API URL: http://localhost:54321
   anon key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
   service_role key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
   ```

   **Copy these keys to `.env` file!**

4. **Create Initial Migration**
   ```bash
   supabase migration new initial_schema
   ```

   This creates: `supabase/migrations/20250114000001_initial_schema.sql`

5. **Create Backend `.env` File**
   ```bash
   # Create .env in project root
   touch .env
   ```

   **Add configuration** (see [File Changes: .env](#1-env-backend-environment-variables))

6. **Apply Migration**
   ```bash
   supabase db reset
   ```

   This:
   - Drops existing database
   - Runs all migrations
   - Applies seed data
   - Recreates schema fresh

7. **Verify in Supabase Studio**
   - Open http://localhost:54323
   - Navigate to Table Editor
   - Verify tables exist: `users`, `files`, `jobs`, `page_results`, etc.
   - Check test user exists in `users` table

8. **Create Storage Buckets**
   ```bash
   # Via Studio UI or SQL:
   INSERT INTO storage.buckets (id, name, public)
   VALUES
     ('ocr-uploads', 'ocr-uploads', false),
     ('ocr-results', 'ocr-results', false);
   ```

9. **Install Python Dependencies**
   ```bash
   pip install supabase postgrest python-dotenv
   # or
   uv add supabase postgrest python-dotenv
   ```

10. **Create Repository Layer** (see [File Changes: Repositories](#6-14-repository-layer))

**Deliverables:**
- ✅ Supabase running locally
- ✅ Database schema applied
- ✅ Test user created
- ✅ Storage buckets created
- ✅ `.env` file configured
- ✅ Repository classes created
- ✅ Supabase client initialized

**Validation:**
```bash
# Test database connection
psql postgresql://postgres:postgres@localhost:54322/postgres -c "\dt"

# Should list all tables
```

---

### Phase 2: Refactor Service Layer (Dual-Write Pattern)

**Goal:** Modify JobManager, FileManager, BatchManager to write to BOTH in-memory AND database.

**Duration:** 4-6 hours

**Strategy:** Additive changes only - existing code continues to work.

```mermaid
sequenceDiagram
    participant API as API Endpoint
    participant JM as JobManager
    participant Memory as In-Memory Dict
    participant Repo as JobRepository
    participant DB as Supabase DB

    API->>JM: create_job(...)
    JM->>Memory: Write job to dict
    Memory-->>JM: Success
    JM->>Repo: create_job(...)
    Repo->>DB: INSERT INTO jobs
    DB-->>Repo: Job created
    Repo-->>JM: Success
    JM->>Repo: create_job_event(...)
    Repo->>DB: INSERT INTO job_events
    DB-->>Repo: Event logged
    JM-->>API: Return job_id

    Note over JM,DB: Dual-write pattern:<br/>Memory + Database
```

**Key Changes:**

1. **Add repository parameters to service constructors**
   - JobManager gets `job_repository`
   - FileManager gets `file_repository` + `supabase_client`
   - BatchManager gets `batch_repository`

2. **Dual-write pattern in all state mutations**
   ```python
   # Example pattern
   def create_job(self, ...):
       # Write to memory (existing)
       job = Job(...)
       with self.job_lock:
           self.jobs[job_id] = job

       # Write to database (new - non-blocking)
       if self.job_repository:
           try:
               asyncio.run_coroutine_threadsafe(
                   self.job_repository.create_job(...),
                   self._event_loop
               ).result(timeout=5)
           except Exception as e:
               logger.error(f"DB write failed: {e}")
               # Don't fail request - fallback to memory
   ```

3. **Log events for audit trail**
   ```python
   # After job state changes
   if self.job_repository:
       asyncio.run_coroutine_threadsafe(
           self.job_repository.create_job_event(
               job_id=UUID(job_id),
               event_type="ocr_page_completed",
               event_data={"page_num": 1, "processing_time": 2.5}
           ),
           self._event_loop
       ).result(timeout=5)
   ```

4. **Store page results**
   ```python
   # After each page completes
   if self.job_repository:
       asyncio.run_coroutine_threadsafe(
           self.job_repository.create_page_result(
               job_id=UUID(job_id),
               page_num=page_num,
               ocr_text=text,
               ocr_processing_time=duration
           ),
           self._event_loop
       ).result(timeout=5)
   ```

5. **Upload to Supabase Storage**
   ```python
   # FileManager.save_upload()
   if self.supabase_client:
       storage_path = f"{user_id}/{file_id}/{filename}"
       self.supabase_client.storage.from_("ocr-uploads").upload(
           path=storage_path,
           file=file_bytes
       )
   ```

**Files Modified:**
- `src/api/main.py` - Initialize repositories
- `src/api/services/job_manager.py` - Dual-write jobs
- `src/api/services/file_manager.py` - Upload to storage + DB
- `src/api/services/batch_manager.py` - Dual-write batches
- `config/settings.py` - Add Supabase settings

**Deliverables:**
- ✅ All job creations written to database
- ✅ All progress updates written to database
- ✅ All events logged to job_events table
- ✅ Files uploaded to Supabase Storage
- ✅ File metadata stored in database
- ✅ In-memory state still works (backward compatible)

**Validation:**
```bash
# Start backend
uvicorn src.api.main:app --reload

# Submit a test job via frontend
# Check Supabase Studio - verify rows in:
# - files table
# - jobs table
# - page_results table (as pages complete)
# - job_events table (audit log)
```

---

### Phase 3: Frontend Realtime Subscriptions

**Goal:** Add Supabase Realtime subscriptions alongside existing SSE.

**Duration:** 3-4 hours

**Strategy:** Dual-subscription - both SSE and Realtime active for comparison.

```mermaid
sequenceDiagram
    participant UI as Frontend Component
    participant SSE as SSE Hook (Old)
    participant RT as Realtime Hook (New)
    participant WS as Supabase Realtime
    participant DB as Supabase DB

    UI->>SSE: useStreamingResults(jobId)
    SSE->>Backend: EventSource connection

    UI->>RT: useRealtimeJob(jobId)
    RT->>DB: Fetch initial job data
    DB-->>RT: Current state
    RT->>WS: Subscribe to channel
    WS-->>RT: Subscription active

    Backend->>DB: UPDATE jobs SET progress=50
    DB->>WS: Broadcast change
    WS->>RT: Job updated event
    RT->>UI: Update state

    Backend->>SSE: Send SSE event
    SSE->>UI: Update state

    Note over UI: Compare both sources<br/>in console logs
```

**Steps:**

1. **Install Supabase JS Client**
   ```bash
   cd web
   npm install @supabase/supabase-js
   ```

2. **Configure Frontend Environment**
   ```bash
   # web/.env.local
   NEXT_PUBLIC_SUPABASE_URL=http://localhost:54321
   NEXT_PUBLIC_SUPABASE_ANON_KEY=<paste-from-supabase-start>
   ```

3. **Create Supabase Client** (see [File: web/lib/supabase.ts](#19-weblibsupabasets))

4. **Create Realtime Hooks** (see [File: web/hooks/useRealtimeJob.ts](#20-webhooksuserealtimedJobts))

5. **Update Components to Use Both**
   ```typescript
   // Example: Job monitoring component
   function JobMonitor({ jobId }: { jobId: string }) {
     // Existing SSE hook (keep for now)
     const { ocrPages: sseOcr } = useStreamingResults(jobId)

     // New Realtime hook (parallel)
     const { pageResults: realtimePages } = useRealtimeJob(jobId)

     // Log both for comparison
     useEffect(() => {
       console.log('SSE pages:', sseOcr.size)
       console.log('Realtime pages:', realtimePages.size)
     }, [sseOcr, realtimePages])

     // Use Realtime data (SSE as fallback)
     const pages = realtimePages.size > 0 ? realtimePages : sseOcr
   }
   ```

6. **Test Realtime Subscriptions**
   - Submit job
   - Open browser DevTools console
   - Watch for `[Realtime] Job updated:` logs
   - Verify pages appear in real-time
   - Compare SSE vs Realtime latency

**Files Created:**
- `web/lib/supabase.ts` - Supabase client
- `web/hooks/useRealtimeJob.ts` - Job subscriptions
- `web/hooks/useRealtimeBatch.ts` - Batch subscriptions

**Files Modified:**
- `web/.env.local` - Add Supabase keys
- `web/package.json` - Add dependency
- Job monitoring components (dual subscription)

**Deliverables:**
- ✅ Frontend connects to Supabase Realtime
- ✅ Job updates received via WebSocket
- ✅ Page results appear in real-time
- ✅ Events logged in console
- ✅ Both SSE and Realtime working in parallel

**Validation:**
- Submit job
- Watch browser console for Realtime logs
- Verify UI updates without polling
- Check WebSocket connection in Network tab

---

### Phase 4: Remove SSE, Use Only Realtime

**Goal:** Validate Realtime stability, remove SSE infrastructure.

**Duration:** 2-3 hours

**Strategy:** Conservative removal - keep SSE code commented for rollback.

```mermaid
graph TD
    A[Compare Metrics] --> B{Realtime Stable?}
    B -->|Yes| C[Remove SSE from Frontend]
    B -->|No| D[Debug/Fix Issues]
    D --> A

    C --> E[Comment SSE Endpoints]
    E --> F[Stop SSE Emissions]
    F --> G[Add Deprecation Warnings]
    G --> H[Test Full Workflow]
    H --> I{All Tests Pass?}
    I -->|Yes| J[Commit Phase 4]
    I -->|No| K[Fix Issues]
    K --> H

    style J fill:#90EE90
```

**Steps:**

1. **Compare Metrics**
   - Latency: SSE vs Realtime
   - Reliability: Connection stability
   - Reconnection: Auto-reconnect behavior
   - Memory: Browser memory usage
   - Server load: Backend CPU/memory

2. **Switch Frontend to Realtime-Only**
   ```typescript
   // Before (dual subscription)
   const { ocrPages: sseOcr } = useStreamingResults(jobId)
   const { pageResults: realtimePages } = useRealtimeJob(jobId)
   const pages = realtimePages.size > 0 ? realtimePages : sseOcr

   // After (Realtime only)
   const { pageResults } = useRealtimeJob(jobId)
   ```

3. **Remove SSE Endpoint (Backend)**
   ```python
   # src/api/processing_routes.py

   # COMMENT OUT (don't delete yet):
   # @router.get("/jobs/{job_id}/stream-results")
   # async def stream_job_results(...):
   #     """DEPRECATED: Use Supabase Realtime"""
   #     ...
   ```

4. **Stop Emitting SSE Events**
   ```python
   # src/api/services/job_manager.py

   # COMMENT OUT ResultEmitter calls:
   # if self.result_emitter:
   #     self.result_emitter.emit_ocr_page(...)
   ```

5. **Remove Polling (Optional)**
   - If Realtime proves reliable, remove status polling
   - Keep initial fetch on mount
   - Rely entirely on Realtime updates

6. **Test Thoroughly**
   - Job submissions
   - Progress updates
   - Page results streaming
   - Batch jobs
   - Error scenarios
   - Network interruptions (WiFi disconnect/reconnect)

**Files Modified:**
- `src/api/processing_routes.py` - Comment SSE endpoint
- `src/api/batch_routes.py` - Comment batch SSE endpoint
- `src/api/services/job_manager.py` - Stop emitting SSE
- `web/hooks/useOcrJob.ts` - Remove SSE subscription
- `web/hooks/useBatchJob.ts` - Remove SSE subscription

**Files Deprecated:**
- `src/api/services/result_emitter.py` - Add deprecation warning
- `src/api/services/progress_emitter.py` - Add deprecation warning
- `web/hooks/useStreamingResults.ts` - Add deprecation warning

**Deliverables:**
- ✅ SSE endpoints disabled
- ✅ Frontend uses only Realtime
- ✅ All features work identically
- ✅ Deprecation warnings added
- ✅ Rollback path documented

**Validation:**
- Run full test suite
- Submit 10+ jobs, verify all complete
- Test batch processing
- Simulate network issues
- Monitor for memory leaks

---

### Phase 5: Remove In-Memory State

**Goal:** Remove dictionaries from managers, read exclusively from database.

**Duration:** 4-6 hours

**Strategy:** Database becomes single source of truth.

```mermaid
graph TD
    A[Remove In-Memory Dicts] --> B[Implement _dict_to_job]
    B --> C[Replace get_job with DB read]
    C --> D[Update all methods]
    D --> E[Handle Cancellation]
    E --> F[Test Restart Persistence]
    F --> G{Jobs Survive Restart?}
    G -->|Yes| H[Test Multi-Instance]
    G -->|No| I[Debug Issues]
    I --> F

    H --> J{Performance OK?}
    J -->|Yes| K[Commit Phase 5]
    J -->|No| L[Add Caching Layer]
    L --> K

    style K fill:#90EE90
```

**Key Changes:**

1. **Remove In-Memory Storage**
   ```python
   # src/api/services/job_manager.py

   # DELETE:
   # self.jobs: Dict[str, Job] = {}
   # self.job_lock = threading.Lock()
   ```

2. **Replace get_job() with Database Read**
   ```python
   # OLD:
   def get_job(self, job_id: str) -> Job:
       with self.job_lock:
           if job_id not in self.jobs:
               raise ValueError(f"Job not found: {job_id}")
           return self.jobs[job_id]

   # NEW:
   def get_job(self, job_id: str) -> Job:
       if not self.job_repository:
           raise RuntimeError("JobRepository not initialized")

       future = asyncio.run_coroutine_threadsafe(
           self.job_repository.get_job(UUID(job_id)),
           self._event_loop
       )
       job_dict = future.result(timeout=5)

       if not job_dict:
           raise ValueError(f"Job not found: {job_id}")

       return self._dict_to_job(job_dict)
   ```

3. **Add Dictionary Converter**
   ```python
   def _dict_to_job(self, job_dict: Dict[str, Any]) -> Job:
       """Convert database dict to Job dataclass."""
       return Job(
           job_id=job_dict["job_id"],
           file_id=job_dict["file_id"],
           filename=job_dict["filename"],
           model=job_dict["model"],
           # ... all fields ...
           status=JobStatus(job_dict["status"]),
           created_at=datetime.fromisoformat(job_dict["created_at"]),
           # ... timestamps ...
       )
   ```

4. **Update All Methods**
   - `create_job()` - Remove dict insert, keep DB write
   - `update_job_progress()` - Only update DB
   - `cancel_job()` - Update DB status
   - `get_job_result()` - Read from DB + filesystem
   - `list_jobs()` - Query DB instead of dict.values()

5. **Handle Cancellation**
   ```python
   # Cancellation requires periodic DB polling (no in-memory flag)
   def _process_job_async(self, job, ...):
       while processing:
           # Check DB for cancel flag every N iterations
           if iteration % 10 == 0:
               current_job = self.get_job(job.job_id)
               if current_job.status == JobStatus.CANCELLED:
                   break
   ```

6. **Similar Changes for FileManager and BatchManager**

**Challenges:**

- **Performance:** Database reads slower than memory
  - Mitigation: Add caching layer (Redis) if needed
  - For now, rely on Supabase connection pooling

- **Thread Safety:** Database handles concurrency
  - No more threading.Lock needed
  - Postgres ACID guarantees consistency

- **Cancellation:** No in-memory flag
  - Poll database periodically
  - Alternative: Use Postgres LISTEN/NOTIFY (future)

**Files Modified:**
- `src/api/services/job_manager.py` - Remove dict, read from DB
- `src/api/services/file_manager.py` - Remove dict, read from DB
- `src/api/services/batch_manager.py` - Remove dict, read from DB

**Files Deleted:**
- None (keep deprecated files for reference)

**Deliverables:**
- ✅ No in-memory job storage
- ✅ All reads from database
- ✅ Jobs survive backend restarts
- ✅ Multiple backend instances can share state
- ✅ Full job history queryable

**Validation:**
```bash
# Test restart persistence
# 1. Start backend, submit job
# 2. While job is running, restart backend
# 3. Job should resume from checkpoint
# 4. Verify job state intact

# Test multi-instance (future)
# 1. Start two backend instances (different ports)
# 2. Submit job to instance A
# 3. Query job from instance B
# 4. Verify both see same state
```

---

### Phase 6: Cloud Deployment (Future)

**Goal:** Deploy to production cloud infrastructure.

**Duration:** 1-2 days (setup + testing)

**Prerequisites:**
- Phases 1-5 complete and tested locally
- Domain name registered (optional)
- Accounts created:
  - Supabase Cloud
  - Vercel
  - Railway
  - Hetzner (or chosen GPU provider)

**Deployment Architecture:** Railway (backend) + Hetzner GEX44 (GPU) + Vercel (frontend)

```mermaid
graph TD
    A[Create Supabase Cloud] --> B[Run Migrations]
    B --> C[Provision Hetzner Server]
    C --> D[Setup VPN/Tailscale]
    D --> E[Deploy to Railway]
    E --> F[Deploy to Vercel]
    F --> G[Update ENV Variables]
    G --> H[DNS Setup]
    H --> I[Enable HTTPS]
    I --> J[Setup Monitoring]
    J --> K{All Services OK?}
    K -->|Yes| L[Load Testing]
    K -->|No| M[Debug Issues]
    M --> K

    L --> N[Documentation]
    N --> O[Commit Phase 6]

    style O fill:#90EE90
```

**Steps:**

1. **Deploy Supabase to Cloud**
   - Create project at supabase.com
   - Run migrations: `supabase db push`
   - Create storage buckets
   - Note: Project URL + keys

2. **Deploy GPU Containers to Hetzner**
   - Provision GEX44 server
   - SSH setup + security hardening
   - Install Docker + NVIDIA drivers
   - Copy docker-compose.yml
   - Start containers
   - Test: `curl http://<hetzner-ip>:8001/health`

3. **Setup VPN/Tunnel (Railway → Hetzner)**
   - Install Tailscale on Hetzner server
   - Install Tailscale on Railway (or use WireGuard)
   - Configure private networking
   - Update backend env: `DEEPSEEK_CONTAINER_URL=http://<tailscale-ip>:8001`

4. **Deploy Backend to Railway**
   - Connect GitHub repo
   - Set environment variables (from `.env`)
   - Railway auto-detects Python + uvicorn
   - Deploy
   - Test: `curl https://<railway-url>/health`

5. **Deploy Frontend to Vercel**
   - Connect GitHub repo
   - Set environment variables
   - Vercel auto-detects Next.js
   - Deploy
   - Test: Open frontend URL

6. **Update Environment Variables**
   - Frontend: `NEXT_PUBLIC_API_URL=https://<railway-url>`
   - Backend: `SUPABASE_URL=https://<project>.supabase.co`
   - Backend: `DEEPSEEK_CONTAINER_URL=http://<tailscale-ip>:8001`

7. **DNS Setup (Optional)**
   - Point custom domain to Vercel
   - Point API subdomain to Railway

8. **Enable HTTPS**
   - Vercel: Automatic
   - Railway: Automatic
   - Hetzner: Nginx reverse proxy + Let's Encrypt

9. **Monitoring & Logging**
   - Railway: Built-in logs
   - Hetzner: Setup logrotate, monitoring
   - Supabase: Built-in monitoring

**Cost Estimates:**
- Supabase Cloud: $25/month (Pro plan)
- Railway: $5-20/month (backend)
- Hetzner GEX44: €184/month (~$200)
- Vercel: $0 (hobby) or $20/month (Pro)
- **Total: ~$250-265/month**

**Deliverables:**
- ✅ Production Supabase database
- ✅ Backend deployed to Railway
- ✅ GPU containers on Hetzner
- ✅ Frontend deployed to Vercel
- ✅ Secure VPN between services
- ✅ HTTPS on all endpoints
- ✅ Monitoring enabled

---

## File Changes Specification

### New Files to Create

#### 1. `.env` (Backend Environment Variables)

**Location:** `/home/jenner/code/ocr-service/.env`

**Purpose:** Centralize backend configuration, enable Supabase connection.

**Content:**
```bash
# Supabase Configuration (Local Development)
SUPABASE_URL=http://localhost:54321
SUPABASE_ANON_KEY=<paste-from-supabase-start>
SUPABASE_SERVICE_KEY=<paste-from-supabase-start>

# Database Direct Connection (optional - for psql/migrations)
DATABASE_URL=postgresql://postgres:postgres@localhost:54322/postgres

# Development Test User
DEV_USER_ID=a0000000-0000-0000-0000-000000000001
DEV_API_KEY=dev_test_key_12345

# Existing Settings (keep current values)
DEFAULT_MODEL=deepseek-ocr
DEEPSEEK_CONTAINER_URL=http://localhost:8001
QWEN_CONTAINER_URL=http://localhost:8002
CONTAINER_TIMEOUT=300.0

API_HOST=0.0.0.0
API_PORT=8000
MAX_UPLOAD_SIZE_MB=50
ENABLE_CORS=true
CORS_ORIGINS=["http://localhost:3000","http://localhost:3001","http://localhost:3002"]

MAX_BATCH_SIZE=10
DEFAULT_OUTPUT_FORMAT=markdown

API_TEMP_DIRECTORY=data/temp
API_PROCESSING_DIRECTORY=data/processing
API_OUTPUT_DIRECTORY=data/output
TEMP_FILE_EXPIRY_HOURS=6
MAX_JOB_HISTORY=100

LOG_LEVEL=INFO
LOG_FORMAT=json

# Supabase Storage Buckets
SUPABASE_STORAGE_BUCKET_UPLOADS=ocr-uploads
SUPABASE_STORAGE_BUCKET_RESULTS=ocr-results
```

**Security Notes:**
- **DO NOT commit this file to git!**
- Add to `.gitignore`
- Service role key has admin privileges (bypass RLS)
- Use anon key for client-side operations

**Cloud Deployment Changes:**
```bash
# Production .env (Railway)
SUPABASE_URL=https://<your-project>.supabase.co
SUPABASE_SERVICE_KEY=<production-service-key>
DEEPSEEK_CONTAINER_URL=http://<tailscale-ip>:8001
QWEN_CONTAINER_URL=http://<tailscale-ip>:8002
```

---

#### 2. `.env.example` (Template)

**Location:** `/home/jenner/code/ocr-service/.env.example`

**Purpose:** Version-controlled template showing required environment variables.

**Content:**
```bash
# Supabase Configuration
SUPABASE_URL=http://localhost:54321
SUPABASE_ANON_KEY=your-anon-key-here
SUPABASE_SERVICE_KEY=your-service-key-here

# Database Connection
DATABASE_URL=postgresql://postgres:postgres@localhost:54322/postgres

# Development User
DEV_USER_ID=a0000000-0000-0000-0000-000000000001
DEV_API_KEY=dev_test_key_12345

# Container URLs
DEEPSEEK_CONTAINER_URL=http://localhost:8001
QWEN_CONTAINER_URL=http://localhost:8002

# ... (rest same as .env)
```

**Usage:**
```bash
# New developer setup
cp .env.example .env
# Edit .env with actual keys from `supabase start`
```

---

#### 3. `supabase/config.toml`

**Location:** `/home/jenner/code/ocr-service/supabase/config.toml`

**Purpose:** Configure Supabase Local services.

**Content:** (Auto-generated by `supabase init`, key customizations below)

**Key Sections:**

```toml
[api]
enabled = true
port = 54321
schemas = ["public", "graphql_public"]
extra_search_path = ["public"]
max_rows = 1000

[db]
port = 54322
major_version = 15

[studio]
enabled = true
port = 54323

[storage]
enabled = true
file_size_limit = "50MiB"

[auth]
enabled = true
site_url = "http://localhost:3000"
additional_redirect_urls = ["http://localhost:3001", "http://localhost:3002"]
# We're using API key auth, not Auth UI, so most auth config is unused

[realtime]
enabled = true
# Tables to broadcast (also set in migration SQL)
# ip_version = "ipv4"
```

**Customizations:**
- Increase `file_size_limit` if processing larger PDFs
- Add CORS origins for frontend development ports

---

#### 4-14. Repository Layer

See [Database Schema Design](#database-schema-design) section for complete SQL.

Below are the Python repository implementations.

---

#### 6. `src/database/__init__.py`

**Location:** `/home/jenner/code/ocr-service/src/database/__init__.py`

**Content:**
```python
"""Database layer for Supabase integration."""
from .supabase_client import get_supabase_client, SupabaseClient, initialize_supabase

__all__ = ["get_supabase_client", "SupabaseClient", "initialize_supabase"]
```

---

#### 7. `src/database/supabase_client.py`

**Location:** `/home/jenner/code/ocr-service/src/database/supabase_client.py`

**Purpose:** Singleton Supabase client wrapper with connection management.

**Content:**
```python
"""Supabase client initialization and management."""
import os
from typing import Optional
from supabase import create_client, Client
from postgrest import APIError
import logging

logger = logging.getLogger(__name__)


class SupabaseClient:
    """Wrapper for Supabase client with connection management."""

    def __init__(self, url: str, service_key: str):
        """Initialize Supabase client.

        Args:
            url: Supabase project URL (e.g., http://localhost:54321)
            service_key: Service role key (bypasses RLS for backend operations)
        """
        self.url = url
        self.service_key = service_key
        self._client: Optional[Client] = None

    def connect(self) -> Client:
        """Connect to Supabase and return client.

        Returns:
            Connected Supabase client instance
        """
        if self._client is None:
            logger.info(f"Connecting to Supabase at {self.url}")
            self._client = create_client(self.url, self.service_key)
            logger.info("✅ Supabase client connected")
        return self._client

    @property
    def client(self) -> Client:
        """Get connected client (lazy connect).

        Returns:
            Supabase client instance
        """
        if self._client is None:
            return self.connect()
        return self._client

    def disconnect(self):
        """Close connection (cleanup on shutdown)."""
        # Supabase Python client doesn't require explicit cleanup,
        # but we track state for testing and lifecycle management
        if self._client:
            logger.info("Disconnecting from Supabase")
            self._client = None


# Global client instance (initialized in main.py lifespan)
_supabase_client: Optional[SupabaseClient] = None


def initialize_supabase(url: str, service_key: str) -> SupabaseClient:
    """Initialize global Supabase client (called once on startup).

    Args:
        url: Supabase project URL
        service_key: Service role key

    Returns:
        Initialized SupabaseClient instance

    Example:
        >>> # In main.py lifespan
        >>> client = initialize_supabase(
        ...     url=settings.supabase_url,
        ...     service_key=settings.supabase_service_key
        ... )
    """
    global _supabase_client
    _supabase_client = SupabaseClient(url, service_key)
    _supabase_client.connect()
    return _supabase_client


def get_supabase_client() -> SupabaseClient:
    """Get global Supabase client instance (dependency injection).

    Returns:
        SupabaseClient instance

    Raises:
        RuntimeError: If client not initialized (call initialize_supabase first)

    Example:
        >>> # In repository constructor
        >>> client = get_supabase_client()
        >>> repo = JobRepository(client.client)
    """
    if _supabase_client is None:
        raise RuntimeError(
            "Supabase client not initialized. "
            "Call initialize_supabase() in main.py lifespan first."
        )
    return _supabase_client
```

**Usage:**
```python
# Initialization (main.py)
from src.database.supabase_client import initialize_supabase

supabase_client = initialize_supabase(
    url=settings.supabase_url,
    service_key=settings.supabase_service_key
)

# Dependency injection (services)
from src.database.supabase_client import get_supabase_client

client = get_supabase_client()
job_repo = JobRepository(client.client)
```

---

#### 8. `src/database/repositories/__init__.py`

**Content:**
```python
"""Repository pattern for database operations."""
from .job_repository import JobRepository
from .file_repository import FileRepository
from .batch_repository import BatchRepository

__all__ = ["JobRepository", "FileRepository", "BatchRepository"]
```

---

#### 9-12. Repository Implementations

**See complete implementations in the plan above under Phase 1, items 9-12.**

Key repositories:
- `base_repository.py` - Generic CRUD operations
- `job_repository.py` - Job lifecycle, events, page results
- `file_repository.py` - File metadata, storage paths
- `batch_repository.py` - Batch job operations

All repositories follow the same pattern:
```python
class XRepository(BaseRepository):
    def __init__(self, client: Client):
        super().__init__(client, "table_name")

    async def create_x(self, ...):
        """Create record with validation."""
        data = {...}
        return await self.create(data)

    async def get_x(self, id: UUID):
        """Get by ID."""
        return await self.get_by_id("id_column", str(id))

    async def update_x(self, id: UUID, ...):
        """Update specific fields."""
        return await self.update("id_column", str(id), data)
```

---

### Files to Modify

#### 15. `config/settings.py` - Add Supabase Configuration

**Location:** `/home/jenner/code/ocr-service/config/settings.py`

**Changes:**

**ADD these fields to the `Settings` class:**

```python
from pydantic_settings import BaseSettings  # Update import if needed
from pydantic import Field
from typing import List

class Settings(BaseSettings):
    # ... existing fields ...

    # ==========================================
    # Supabase Configuration (NEW)
    # ==========================================
    supabase_url: str = Field(
        default="http://localhost:54321",
        description="Supabase project URL"
    )
    supabase_anon_key: str = Field(
        default="",
        description="Supabase anonymous key (for client-side)"
    )
    supabase_service_key: str = Field(
        default="",
        description="Supabase service role key (bypasses RLS, for backend)"
    )

    # Storage Configuration (NEW)
    supabase_storage_bucket_uploads: str = "ocr-uploads"
    supabase_storage_bucket_results: str = "ocr-results"

    # Development Test User (NEW)
    dev_user_id: str = "a0000000-0000-0000-0000-000000000001"
    dev_api_key: str = "dev_test_key_12345"

    class Config:
        env_file = ".env"  # ADD THIS - enable .env loading
        env_file_encoding = "utf-8"
        case_sensitive = False
```

**Reason:**
- Centralize all Supabase configuration
- Load from `.env` file automatically
- Provide defaults for local development
- Type validation via Pydantic

**Usage:**
```python
from config.settings import settings

# Access anywhere
print(settings.supabase_url)  # http://localhost:54321
```

---

## Deployment Architecture

### Local Development (Phases 1-5)

**Services:**
```mermaid
graph TB
    subgraph Local["Local Machine - 2x RTX 4090"]
        SB[Supabase Local Docker<br/>PostgreSQL: localhost:54322<br/>API: localhost:54321<br/>Studio: localhost:54323]

        BE[FastAPI Backend<br/>uvicorn: localhost:8000]

        FE[Next.js Frontend<br/>npm run dev: localhost:3000]

        DC[GPU Containers<br/>DeepSeek: localhost:8001 GPU 0<br/>Qwen3-VL: localhost:8002 GPU 1]
    end

    FE <-->|HTTP/WS| BE
    FE <-->|Realtime WSS| SB
    BE <-->|SQL| SB
    BE <-->|HTTP| DC

    style SB fill:#3ecf8e
    style BE fill:#7c3aed
    style FE fill:#000
    style DC fill:#d50c2d
```

**Start Commands:**
```bash
# Terminal 1: Supabase
supabase start

# Terminal 2: GPU Containers
docker-compose up

# Terminal 3: Backend
uvicorn src.api.main:app --reload

# Terminal 4: Frontend
cd web && npm run dev
```

**Environment Variables:**
```bash
# Backend .env
SUPABASE_URL=http://localhost:54321
SUPABASE_SERVICE_KEY=<from-supabase-start>
DEEPSEEK_CONTAINER_URL=http://localhost:8001
QWEN_CONTAINER_URL=http://localhost:8002

# Frontend .env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=http://localhost:54321
NEXT_PUBLIC_SUPABASE_ANON_KEY=<from-supabase-start>
```

---

## Testing Strategy

### Unit Tests

**Repository Tests** (`tests/database/test_repositories.py`):

```python
import pytest
from uuid import uuid4
from src.database.repositories import JobRepository, FileRepository

@pytest.mark.asyncio
async def test_create_job(supabase_client):
    """Test job creation in database."""
    repo = JobRepository(supabase_client)

    user_id = uuid4()
    file_id = uuid4()

    job = await repo.create_job(
        user_id=user_id,
        file_id=file_id,
        filename="test.pdf",
        model="deepseek-ocr",
        prompt_type="markdown",
        custom_prompts=None,
        processing_options={},
        output_format="markdown"
    )

    assert job["job_id"] is not None
    assert job["status"] == "queued"
    assert job["filename"] == "test.pdf"

@pytest.mark.asyncio
async def test_update_job_progress(supabase_client):
    """Test job progress updates."""
    repo = JobRepository(supabase_client)

    # Create job
    job = await repo.create_job(...)
    job_id = job["job_id"]

    # Update progress
    updated = await repo.update_job_progress(
        job_id=uuid.UUID(job_id),
        progress_pct=50.0,
        pages_completed=5,
        current_stage="ocr"
    )

    assert updated["progress_pct"] == 50.0
    assert updated["pages_completed"] == 5

@pytest.mark.asyncio
async def test_page_results(supabase_client):
    """Test page result storage."""
    repo = JobRepository(supabase_client)

    job = await repo.create_job(...)
    job_id = job["job_id"]

    # Create page result
    page = await repo.create_page_result(
        job_id=uuid.UUID(job_id),
        page_num=1,
        ocr_text="Sample OCR text",
        ocr_processing_time=2.5
    )

    assert page["page_num"] == 1
    assert page["ocr_text"] == "Sample OCR text"

    # Update with merge text (upsert)
    updated = await repo.create_page_result(
        job_id=uuid.UUID(job_id),
        page_num=1,
        merge_text="Refined text"
    )

    assert updated["ocr_text"] == "Sample OCR text"  # Preserved
    assert updated["merge_text"] == "Refined text"  # Added

@pytest.mark.asyncio
async def test_job_events(supabase_client):
    """Test event logging."""
    repo = JobRepository(supabase_client)

    job = await repo.create_job(...)
    job_id = job["job_id"]

    # Log event
    event = await repo.create_job_event(
        job_id=uuid.UUID(job_id),
        event_type="ocr_page_completed",
        event_data={"page_num": 1, "processing_time": 2.5}
    )

    assert event["event_type"] == "ocr_page_completed"

    # Query events
    events = await repo.get_job_events(uuid.UUID(job_id))
    assert len(events) >= 1
```

---

## Migration Checklist

### Pre-Migration

- [ ] Review current architecture documentation
- [ ] Back up existing data (if any production data)
- [ ] Create feature branch: `git checkout -b feature/supabase-migration`
- [ ] Install Supabase CLI
- [ ] Verify Docker is running

---

### Phase 1: Setup (Estimated: 2-3 hours)

- [ ] Run `supabase init`
- [ ] Run `supabase start`
- [ ] Copy anon key and service key from output
- [ ] Create `.env` file with Supabase credentials
- [ ] Create `.env.example` template
- [ ] Add `.env` to `.gitignore`
- [ ] Create migration file: `supabase/migrations/20250114000001_initial_schema.sql`
- [ ] Copy complete schema SQL from specification
- [ ] Run `supabase db reset` to apply migration
- [ ] Open Studio (localhost:54323), verify tables exist
- [ ] Create storage buckets (`ocr-uploads`, `ocr-results`)
- [ ] Insert test user (if not in seed data)
- [ ] Install Python dependencies: `pip install supabase postgrest python-dotenv`
- [ ] Create `src/database/` directory structure
- [ ] Implement `supabase_client.py`
- [ ] Implement `repositories/base_repository.py`
- [ ] Implement `repositories/job_repository.py`
- [ ] Implement `repositories/file_repository.py`
- [ ] Implement `repositories/batch_repository.py`
- [ ] Write repository unit tests
- [ ] Run tests: `pytest tests/database/`
- [ ] Commit: `git commit -m "Phase 1: Supabase setup and repositories"`

---

### Phase 2: Dual-Write (Estimated: 4-6 hours)

- [ ] Update `config/settings.py` with Supabase settings
- [ ] Modify `src/api/main.py` lifespan to initialize Supabase
- [ ] Update `JobManager.__init__()` to accept `job_repository`
- [ ] Update `FileManager.__init__()` to accept `file_repository` + `supabase_client`
- [ ] Update `BatchManager.__init__()` to accept `batch_repository`
- [ ] Implement dual-write in `JobManager.create_job()`
- [ ] Implement dual-write in `JobManager.update_job_progress()`
- [ ] Add page result writes in `JobManager._process_job_async()`
- [ ] Add event logging throughout job lifecycle
- [ ] Implement Supabase Storage upload in `FileManager.save_upload()`
- [ ] Implement file metadata DB write in `FileManager.save_upload()`
- [ ] Implement dual-write in `BatchManager.create_batch_job()`
- [ ] Test: Start backend, submit job via frontend
- [ ] Verify rows appear in Supabase Studio:
  - [ ] `files` table
  - [ ] `jobs` table
  - [ ] `page_results` table (as pages complete)
  - [ ] `job_events` table
- [ ] Verify file uploaded to Storage bucket
- [ ] Check logs for any database write errors
- [ ] Run existing test suite (should still pass)
- [ ] Commit: `git commit -m "Phase 2: Dual-write to database"`

---

### Phase 3: Realtime (Estimated: 3-4 hours)

- [ ] Install frontend dependency: `cd web && npm install @supabase/supabase-js`
- [ ] Copy anon key to `web/.env.local`
- [ ] Create `web/lib/supabase.ts` with client initialization
- [ ] Create `web/hooks/useRealtimeJob.ts`
- [ ] Create `web/hooks/useRealtimeBatch.ts`
- [ ] Update job monitoring component to use dual subscription (SSE + Realtime)
- [ ] Test: Submit job, watch browser console for Realtime logs
- [ ] Verify page results appear in real-time
- [ ] Verify job status updates without polling
- [ ] Check Network tab for WebSocket connection
- [ ] Compare latency: SSE vs Realtime
- [ ] Test reconnection: Disconnect WiFi, reconnect, verify subscription resumes
- [ ] Run frontend tests
- [ ] Commit: `git commit -m "Phase 3: Add Realtime subscriptions"`

---

### Phase 4: Remove SSE (Estimated: 2-3 hours)

- [ ] Document comparison metrics (SSE vs Realtime)
- [ ] Update components to use Realtime only (remove SSE hooks)
- [ ] Comment out SSE endpoint in `processing_routes.py`
- [ ] Comment out SSE endpoint in `batch_routes.py`
- [ ] Stop emitting SSE events in `JobManager`
- [ ] Add deprecation warnings to `result_emitter.py` and `progress_emitter.py`
- [ ] Remove status polling (if Realtime reliable enough)
- [ ] Test full workflow: upload → submit → monitor → result
- [ ] Test error scenarios (job failure, cancellation)
- [ ] Test network interruptions
- [ ] Monitor for memory leaks (browser dev tools)
- [ ] Run full test suite
- [ ] Commit: `git commit -m "Phase 4: Remove SSE, use Realtime only"`

---

### Phase 5: Database-Only (Estimated: 4-6 hours)

- [ ] Remove `self.jobs: Dict[str, Job] = {}` from `JobManager`
- [ ] Remove `self.job_lock` from `JobManager`
- [ ] Implement `_dict_to_job()` converter in `JobManager`
- [ ] Replace `get_job()` to read from database
- [ ] Update `create_job()` to only write to database
- [ ] Update `update_job_progress()` to only write to database
- [ ] Add periodic cancellation check (poll database)
- [ ] Similar changes for `FileManager` and `BatchManager`
- [ ] Test: Submit job, restart backend mid-processing
- [ ] Verify job resumes from checkpoint (if implemented)
- [ ] Verify job state intact after restart
- [ ] Test: Query job from different backend instance (future)
- [ ] Run performance tests (database vs memory)
- [ ] Add caching layer if needed (Redis)
- [ ] Run full test suite
- [ ] Commit: `git commit -m "Phase 5: Database as single source of truth"`

---

### Phase 6: Cloud Deployment (Estimated: 1-2 days)

- [ ] Create Supabase Cloud project
- [ ] Run migrations: `supabase link --project-ref <ref> && supabase db push`
- [ ] Create storage buckets in cloud
- [ ] Provision Hetzner GEX44 server (or chosen GPU provider)
- [ ] Setup SSH, security, Docker, NVIDIA drivers on Hetzner
- [ ] Copy docker-compose.yml to Hetzner
- [ ] Start GPU containers on Hetzner
- [ ] Setup Tailscale/WireGuard VPN (Railway ↔ Hetzner)
- [ ] Deploy backend to Railway (connect GitHub)
- [ ] Set Railway environment variables
- [ ] Test Railway → Hetzner VPN connection
- [ ] Deploy frontend to Vercel (connect GitHub)
- [ ] Set Vercel environment variables
- [ ] Update DNS (optional)
- [ ] Test end-to-end in production
- [ ] Setup monitoring (Railway logs, Supabase dashboard)
- [ ] Load testing
- [ ] Documentation update
- [ ] Commit: `git commit -m "Phase 6: Production deployment"`

---

### Post-Migration

- [ ] Update README with new architecture
- [ ] Document deployment process
- [ ] Create runbook for common operations
- [ ] Setup alerts/monitoring
- [ ] Performance tuning
- [ ] Cost optimization review
- [ ] Team training (if applicable)
- [ ] Archive old in-memory code (don't delete yet)
- [ ] Create tag: `git tag v2.0.0-supabase`
- [ ] Merge to main: `git checkout main && git merge feature/supabase-migration`

---

## Appendix

### Environment Variables Reference

**Backend (.env):**
```bash
# Supabase
SUPABASE_URL=http://localhost:54321
SUPABASE_ANON_KEY=<anon-key>
SUPABASE_SERVICE_KEY=<service-key>
DATABASE_URL=postgresql://postgres:postgres@localhost:54322/postgres

# Development
DEV_USER_ID=a0000000-0000-0000-0000-000000000001
DEV_API_KEY=dev_test_key_12345

# Containers
DEEPSEEK_CONTAINER_URL=http://localhost:8001
QWEN_CONTAINER_URL=http://localhost:8002

# Storage
SUPABASE_STORAGE_BUCKET_UPLOADS=ocr-uploads
SUPABASE_STORAGE_BUCKET_RESULTS=ocr-results

# API
API_HOST=0.0.0.0
API_PORT=8000
```

**Frontend (.env.local):**
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=http://localhost:54321
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon-key>
```

---

### Useful Commands

**Supabase:**
```bash
# Start local stack
supabase start

# Stop local stack
supabase stop

# Reset database (apply all migrations)
supabase db reset

# Create new migration
supabase migration new <name>

# View database
psql postgresql://postgres:postgres@localhost:54322/postgres

# Studio UI
open http://localhost:54323
```

**Testing:**
```bash
# Run repository tests
pytest tests/database/ -v

# Run integration tests
pytest tests/integration/ -v

# Run all tests
pytest

# Frontend tests
cd web && npm test
```

**Development:**
```bash
# Start all services
# Terminal 1:
supabase start

# Terminal 2:
docker-compose up

# Terminal 3:
uvicorn src.api.main:app --reload

# Terminal 4:
cd web && npm run dev
```

---

### Troubleshooting

**Issue: Supabase won't start**
```bash
# Check Docker is running
docker ps

# Check ports not in use
lsof -i :54321
lsof -i :54322

# Reset Supabase
supabase stop
supabase start
```

**Issue: Database write failures**
```bash
# Check service key is correct
echo $SUPABASE_SERVICE_KEY

# Check database connection
psql $DATABASE_URL -c "SELECT 1"

# Check logs
tail -f logs/app.log
```

**Issue: Realtime not working**
```bash
# Check browser console for errors
# Verify anon key in frontend .env.local
# Check Supabase Studio: Database > Replication
# Verify tables added to publication
```

**Issue: Files not uploading to Storage**
```bash
# Check bucket exists
# Verify storage permissions
# Check file size limits
# Review backend logs for errors
```

---

### Success Criteria

**Phase 1 Complete:**
- ✅ Supabase running locally
- ✅ All tables created
- ✅ Test user exists
- ✅ Repositories passing unit tests

**Phase 2 Complete:**
- ✅ Jobs written to database
- ✅ Events logged to job_events
- ✅ Files uploaded to Storage
- ✅ In-memory state still works

**Phase 3 Complete:**
- ✅ Frontend receives Realtime updates
- ✅ Pages appear without polling
- ✅ WebSocket connection stable

**Phase 4 Complete:**
- ✅ SSE endpoints disabled
- ✅ Frontend uses only Realtime
- ✅ All features work identically

**Phase 5 Complete:**
- ✅ Jobs survive restarts
- ✅ No in-memory state
- ✅ Database is single source of truth

**Phase 6 Complete:**
- ✅ Production deployment live
- ✅ All services communicating
- ✅ Monitoring enabled
- ✅ Performance acceptable

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-01-14 | AI Assistant | Initial specification |
| 1.1 | 2025-01-14 | AI Assistant | Converted ASCII diagrams to Mermaid |
| 1.2 | 2025-01-14 | AI Assistant | Corrected arrow directions to bidirectional for request-response patterns |

---

**END OF SPECIFICATION**
