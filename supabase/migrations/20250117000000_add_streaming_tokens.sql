-- Phase 4: Add streaming_tokens table for database-based token streaming
-- This replaces SSE-based streaming with Supabase Realtime subscriptions

-- Create streaming_tokens table
CREATE TABLE IF NOT EXISTS streaming_tokens (
    token_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    page_num INTEGER NOT NULL,
    chunk_sequence INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Ensure unique ordering for chunks
    UNIQUE(job_id, page_num, chunk_sequence)
);

-- Add index for efficient queries by job_id and page_num
CREATE INDEX idx_streaming_tokens_job_page
    ON streaming_tokens(job_id, page_num, chunk_sequence);

-- Add index for cleanup queries
CREATE INDEX idx_streaming_tokens_job
    ON streaming_tokens(job_id);

-- Enable Row Level Security
ALTER TABLE streaming_tokens ENABLE ROW LEVEL SECURITY;

-- Allow all authenticated users to read streaming tokens
CREATE POLICY "Allow authenticated read access to streaming_tokens"
    ON streaming_tokens
    FOR SELECT
    TO authenticated
    USING (true);

-- Allow service role to insert/delete streaming tokens
CREATE POLICY "Allow service role full access to streaming_tokens"
    ON streaming_tokens
    FOR ALL
    TO service_role
    USING (true);

-- Enable Realtime for streaming_tokens table
ALTER PUBLICATION supabase_realtime ADD TABLE streaming_tokens;

-- Add comment
COMMENT ON TABLE streaming_tokens IS
'Phase 4: Stores streaming token chunks for real-time frontend display via Supabase Realtime. Replaces deprecated SSE-based streaming.';
