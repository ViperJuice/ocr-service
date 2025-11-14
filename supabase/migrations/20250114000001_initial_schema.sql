-- OCR Service Initial Database Schema
-- Phase 1: Supabase Migration
-- Date: 2025-01-14

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- Table: users - User Authentication
-- ============================================
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

-- ============================================
-- Table: files - File Metadata
-- ============================================
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
    FOR ALL USING (user_id = current_setting('app.user_id', true)::uuid);

-- ============================================
-- Table: batch_jobs - Batch Processing
-- ============================================
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
    FOR ALL USING (user_id = current_setting('app.user_id', true)::uuid);

-- Enable Realtime
ALTER PUBLICATION supabase_realtime ADD TABLE batch_jobs;

-- ============================================
-- Table: jobs - OCR Processing Jobs
-- ============================================
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
    parent_batch_id UUID REFERENCES batch_jobs(batch_job_id) ON DELETE CASCADE,

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
    FOR ALL USING (user_id = current_setting('app.user_id', true)::uuid);

-- Enable Realtime
ALTER PUBLICATION supabase_realtime ADD TABLE jobs;

-- ============================================
-- Table: page_results - Per-Page OCR Results
-- ============================================
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
    FOR ALL USING (job_id IN (SELECT job_id FROM jobs WHERE user_id = current_setting('app.user_id', true)::uuid));

-- Enable Realtime
ALTER PUBLICATION supabase_realtime ADD TABLE page_results;

-- ============================================
-- Table: job_events - Audit Log (Event Sourcing)
-- ============================================
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
    FOR ALL USING (job_id IN (SELECT job_id FROM jobs WHERE user_id = current_setting('app.user_id', true)::uuid));

-- Enable Realtime
ALTER PUBLICATION supabase_realtime ADD TABLE job_events;

-- ============================================
-- Table: directories - Multi-File Upload Groups
-- ============================================
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
    FOR ALL USING (user_id = current_setting('app.user_id', true)::uuid);

-- ============================================
-- Table: directory_files - Junction Table
-- ============================================
CREATE TABLE directory_files (
    directory_id UUID NOT NULL REFERENCES directories(directory_id) ON DELETE CASCADE,
    file_id UUID NOT NULL REFERENCES files(file_id) ON DELETE CASCADE,
    sequence_num INTEGER NOT NULL,

    PRIMARY KEY (directory_id, file_id),
    UNIQUE (directory_id, sequence_num)
);

-- Indexes
CREATE INDEX idx_directory_files_directory ON directory_files(directory_id, sequence_num);

-- ============================================
-- Seed Data: Test User
-- ============================================
INSERT INTO users (user_id, email, api_key, created_at, is_active)
VALUES (
    'a0000000-0000-0000-0000-000000000001'::uuid,
    'dev@test.com',
    'dev_test_key_12345',
    NOW(),
    true
) ON CONFLICT DO NOTHING;
