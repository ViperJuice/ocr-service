// ============================================================================
// Core Types
// ============================================================================

export type OutputFormat = "markdown" | "text" | "json";

export interface ProcessingOptions {
  dpi?: number;
  method?: "auto" | "extract" | "ocr" | "hybrid";
  start_page?: number;
  end_page?: number;
  staged_pipeline?: boolean;
  prefer_quality?: boolean;
}

export type CustomPrompts = Record<string, string>;

// ============================================================================
// File Upload Types
// ============================================================================

export interface FileMetadata {
  file_id: string;
  filename: string;
  size_bytes: number;
  mime_type: string;
  uploaded_at: string;
  expires_at: string;
  page_count?: number;
}

export interface DirectoryInfo {
  directory_id: string;
  name: string;
  file_count: number;
  total_size: number;
  files: Array<{
    file_id: string;
    filename: string;
    size: number;
    page_count?: number;
  }>;
}

// ============================================================================
// Job Types
// ============================================================================

export type JobStatus = "queued" | "processing" | "completed" | "failed" | "cancelled";

export interface JobSubmitRequest {
  file_id: string;
  model?: string;
  prompt_type?: string;
  custom_prompts?: CustomPrompts;
  processing_options?: ProcessingOptions;
  output_format?: OutputFormat;
}

export interface JobCreatedResponse {
  job_id: string;
  status: "queued";
  created_at: string;
  file_id: string;
  estimated_pages?: number;
  monitor_url: string;
}

export interface JobStatusResponse {
  job_id: string;
  status: JobStatus;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  file_id: string;
  filename: string;
  total_pages?: number;
  pages_completed: number;
  current_stage?: string;
  progress_pct: number;
  estimated_remaining_seconds?: number;
  error?: string;
}

export interface JobResult {
  job_id: string;
  status: "completed";
  result: {
    format: OutputFormat;
    content: string;
    total_pages?: number;
    processing_time_seconds: number;
    model_used: string;
    metadata: {
      dpi: number;
      method: string;
      pages_processed: number;
    };
  };
  completed_at: string;
}

// ============================================================================
// Batch Types
// ============================================================================

export type BatchJobStatusType = "queued" | "processing" | "completed" | "failed" | "cancelled";

export interface BatchJobStatus {
  batch_job_id: string;
  directory_id: string;
  total_documents: number;
  documents_completed: number;
  overall_progress_pct: number;
  status: BatchJobStatusType;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  error?: string;
}

export interface DocumentProgress {
  job_id: string;
  filename: string;
  progress_pct: number;
  current_page?: number;
  total_pages?: number;
  stage?: string;
  status: JobStatus;
  isCurrent?: boolean;
  isCompact?: boolean;
}

export interface BatchProgress {
  batch_job_id: string;
  overall_progress_pct: number;
  documents_completed: number;
  total_documents: number;
  current_document: DocumentProgress | null;
}

export interface BatchResultResponse {
  batch_job_id: string;
  total_documents: number;
  documents_completed: number;
  results: Array<{
    job_id: string;
    filename: string;
    format?: string;
    content?: string;
    total_pages?: number;
    status: string;
    error?: string;
  }>;
  overall_processing_time_seconds: number;
}

// ============================================================================
// Inline Progress Types
// ============================================================================

export interface InlineProgressData {
  type: "single" | "multi-page" | "batch";
  progress_pct: number;
  content: string;
  currentPage?: number;
  totalPages?: number;
  documentsCompleted?: number;
  totalDocuments?: number;
  currentDocument?: string;
  stage?: string;
}

// ============================================================================
// Chat Message Types
// ============================================================================

export interface ChatMessage {
  id: string;
  role: "user" | "system" | "assistant";
  content: string;
  timestamp: number;
  metadata?: {
    jobId?: string;
    batchJobId?: string;
    fileId?: string;
    fileName?: string;
    [key: string]: any;
  };
  inlineProgress?: InlineProgressData;
}

// Alert type for AlertBanner component
export interface Alert {
  id: string;
  type: "info" | "warning" | "error" | "success";
  message: string;
  dismissible?: boolean;
}

// Monitoring types for legacy ProgressMonitor component
export interface MonitoringMetrics {
  timestamp: string;
  job_id?: string;
  event_type?: string;
  [key: string]: any;
}

// ============================================================================
// SSE Event Types
// ============================================================================

export interface JobProgressEvent {
  event: "job_progress";
  data: {
    job_id: string;
    status: string;
    progress_pct: number;
    current_page: number;
    total_pages?: number;
    stage: string;
    pages_completed: number;
    parent_batch_id?: string;
  };
}

export interface BatchProgressEvent {
  event: "batch_progress";
  data: {
    batch_job_id: string;
    status: string;
    overall_progress_pct: number;
    documents_completed: number;
    total_documents: number;
    current_document?: {
      job_id: string;
      filename: string;
      progress_pct: number;
      current_page: number;
      total_pages: number;
      stage: string;
    };
  };
}

export interface DocumentProgressEvent {
  event: "document_progress";
  data: {
    batch_job_id: string;
    job_id: string;
    filename: string;
    progress_pct: number;
    current_page: number;
    total_pages: number;
    stage: string;
    status: string;
  };
}

export interface BatchCompleteEvent {
  event: "batch_complete";
  data: {
    batch_job_id: string;
    total_documents: number;
    documents_completed: number;
    documents_failed: number;
    overall_processing_time_seconds: number;
  };
}

export interface ErrorEvent {
  event: "error";
  data: {
    job_id?: string;
    batch_job_id?: string;
    error_message: string;
    error_type: string;
    recoverable: boolean;
  };
}

export type SSEEvent =
  | JobProgressEvent
  | BatchProgressEvent
  | DocumentProgressEvent
  | BatchCompleteEvent
  | ErrorEvent;

// ============================================================================
// System Monitoring Types
// ============================================================================

export interface SystemMetrics {
  timestamp: string;
  cpu_percent: number;
  memory_percent: number;
  gpu_stats?: Array<{
    index: number;
    name: string;
    memory_used_mb: number;
    memory_total_mb: number;
    utilization_percent: number;
    temperature_c?: number;
  }>;
  active_jobs: number;
  queued_jobs: number;
}
