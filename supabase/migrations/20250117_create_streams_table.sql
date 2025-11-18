-- Migration: Phase 4 - Single Mutable Row Streaming Architecture
-- Description: Replace append-only streaming_tokens with single mutable streams table
-- Created: 2025-01-17

-- ==================== Drop Old Table ====================

DROP TABLE IF EXISTS streaming_tokens CASCADE;

-- ==================== Create Streams Table ====================

CREATE TABLE streams (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
  page_num INTEGER NOT NULL,
  stage TEXT NOT NULL CHECK (stage IN ('ocr', 'merge', 'complete', 'failed')),
  snapshot_text TEXT,
  seq INTEGER NOT NULL DEFAULT 0,
  is_final BOOLEAN NOT NULL DEFAULT false,
  error JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- Enforce single row per (job_id, page_num)
  UNIQUE(job_id, page_num)
);

-- ==================== Indexes ====================

-- Primary lookup index for frontend subscriptions
CREATE INDEX idx_streams_job_page ON streams(job_id, page_num);

-- Index for job cleanup operations
CREATE INDEX idx_streams_job_id ON streams(job_id);

-- Index for monitoring/debugging by stage
CREATE INDEX idx_streams_stage ON streams(stage);

-- ==================== Row Level Security ====================

-- Enable RLS
ALTER TABLE streams ENABLE ROW LEVEL SECURITY;

-- Policy: Users can read their own streams
CREATE POLICY "Users can read own streams"
  ON streams
  FOR SELECT
  USING (
    job_id IN (
      SELECT job_id FROM jobs WHERE user_id = auth.uid()
    )
  );

-- Policy: Service role can do everything (backend operations)
CREATE POLICY "Service role has full access"
  ON streams
  FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- ==================== Realtime Publication ====================

-- Add streams table to Realtime publication for WebSocket subscriptions
ALTER PUBLICATION supabase_realtime ADD TABLE streams;

-- ==================== Helper Functions ====================

-- Function: Atomically update stream snapshot with seq increment
-- This prevents race conditions when multiple writes happen concurrently
CREATE OR REPLACE FUNCTION update_stream_snapshot(
  p_job_id UUID,
  p_page_num INTEGER,
  p_snapshot_text TEXT,
  p_stage TEXT DEFAULT 'merge',
  p_is_final BOOLEAN DEFAULT false,
  p_error JSONB DEFAULT NULL
) RETURNS INTEGER AS $$
DECLARE
  v_new_seq INTEGER;
BEGIN
  -- Upsert: insert if not exists, update if exists
  INSERT INTO streams (job_id, page_num, stage, snapshot_text, seq, is_final, error, updated_at)
  VALUES (p_job_id, p_page_num, p_stage, p_snapshot_text, 1, p_is_final, p_error, now())
  ON CONFLICT (job_id, page_num)
  DO UPDATE SET
    stage = EXCLUDED.stage,
    snapshot_text = EXCLUDED.snapshot_text,
    seq = streams.seq + 1,  -- Atomic increment
    is_final = EXCLUDED.is_final,
    error = EXCLUDED.error,
    updated_at = now()
  RETURNING seq INTO v_new_seq;

  RETURN v_new_seq;
END;
$$ LANGUAGE plpgsql;

-- Function: Mark stream stage without updating snapshot (for stage transitions)
CREATE OR REPLACE FUNCTION mark_stream_stage(
  p_job_id UUID,
  p_page_num INTEGER,
  p_stage TEXT
) RETURNS VOID AS $$
BEGIN
  INSERT INTO streams (job_id, page_num, stage, snapshot_text, seq, updated_at)
  VALUES (p_job_id, p_page_num, p_stage, '', 0, now())
  ON CONFLICT (job_id, page_num)
  DO UPDATE SET
    stage = EXCLUDED.stage,
    seq = streams.seq + 1,
    updated_at = now();
END;
$$ LANGUAGE plpgsql;

-- Function: Mark stream as complete with final snapshot
CREATE OR REPLACE FUNCTION mark_stream_complete(
  p_job_id UUID,
  p_page_num INTEGER,
  p_final_text TEXT
) RETURNS VOID AS $$
BEGIN
  UPDATE streams
  SET
    stage = 'complete',
    snapshot_text = p_final_text,
    is_final = true,
    seq = seq + 1,
    updated_at = now()
  WHERE job_id = p_job_id AND page_num = p_page_num;
END;
$$ LANGUAGE plpgsql;

-- Function: Mark stream as failed with error details
CREATE OR REPLACE FUNCTION mark_stream_failed(
  p_job_id UUID,
  p_page_num INTEGER,
  p_error JSONB
) RETURNS VOID AS $$
BEGIN
  UPDATE streams
  SET
    stage = 'failed',
    is_final = true,
    error = p_error,
    seq = seq + 1,
    updated_at = now()
  WHERE job_id = p_job_id AND page_num = p_page_num;
END;
$$ LANGUAGE plpgsql;

-- ==================== Comments ====================

COMMENT ON TABLE streams IS 'Phase 4: Single mutable row per stream with snapshot updates (replaces streaming_tokens)';
COMMENT ON COLUMN streams.stage IS 'Pipeline stage: ocr | merge | complete | failed';
COMMENT ON COLUMN streams.snapshot_text IS 'Accumulated text snapshot (throttled writes)';
COMMENT ON COLUMN streams.seq IS 'Monotonic sequence number for deduplication';
COMMENT ON COLUMN streams.is_final IS 'True when stream is complete or failed';
COMMENT ON COLUMN streams.error IS 'Error details if stage=failed';
COMMENT ON FUNCTION update_stream_snapshot IS 'Atomically update snapshot with seq increment';
COMMENT ON FUNCTION mark_stream_stage IS 'Transition to new stage without snapshot update';
COMMENT ON FUNCTION mark_stream_complete IS 'Mark stream complete with final text';
COMMENT ON FUNCTION mark_stream_failed IS 'Mark stream failed with error details';
