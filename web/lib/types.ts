// ============================================================================
// BAML-Generated Types
// ============================================================================

// Import BAML-generated types (single source of truth)
import type {
  ProcessingOptions,
  OCRJobParameters,
  FormatReference,
  PageRange,
  UserIntent,
  RefactoredPrompts,
  ToolCall,
  ToolCallSequence,
  ValidationResult,
  OrchestrationResult,
} from "@/lib/baml-wrapper";

// Re-export BAML types for convenience
export type {
  ProcessingOptions,
  OCRJobParameters,
  FormatReference,
  PageRange,
  UserIntent,
  RefactoredPrompts,
  ToolCall,
  ToolCallSequence,
  ValidationResult,
  OrchestrationResult,
};

// Backward compatibility aliases
export type JobSubmitRequest = OCRJobParameters;
export type CustomPrompts = Record<string, string>;

// ============================================================================
// Core Types
// ============================================================================

export type OutputFormat = "markdown" | "text" | "json";

// SavedPrompt is frontend-specific (not from BAML)
export interface SavedPrompt {
  id: string;
  name: string;
  category: string;
  description: string;
  prompts: CustomPrompts;
  createdAt: number;
  updatedAt: number;
}

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

// Note: JobSubmitRequest is now an alias to OCRJobParameters (defined at top)

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
    deepseek_ocr_content?: string;
    original_file_url?: string;
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

// ============================================================================
// Streaming Result Events (for real-time OCR/merge results)
// ============================================================================

export interface OcrPageCompleteEvent {
  event: "ocr_page_complete";
  data: {
    page_num: number;
    text: string;
    timestamp: string;
    model?: string;  // Optional model identifier (e.g., "deepseek-ai/DeepSeek-OCR")
  };
}

export interface MergePageCompleteEvent {
  event: "merge_page_complete";
  data: {
    page_num: number;
    text: string;
    timestamp: string;
    processing_time?: number;  // Processing time in seconds
    total_pages?: number;      // Total pages in job
    model?: string;            // Optional model identifier (e.g., "Qwen/Qwen3-VL-8B-Instruct")
    streaming_complete?: boolean;  // Whether this page was completed via streaming
  };
}

export interface MergeChunkEvent {
  event: "merge_chunk";
  data: {
    page_num: number;
    chunk: string;
    is_final: boolean;
    timestamp: string;
  };
}

export interface StageCompleteEvent {
  event: "stage_complete";
  data: {
    stage: "ocr" | "merge";
    timestamp: string;
  };
}

export interface JobCompleteEvent {
  event: "job_complete";
  data: {
    timestamp: string;
  };
}

export interface SystemMessageEvent {
  event: "system_message";
  data: {
    message: string;
    metadata: Record<string, any>;
    timestamp: string;
  };
}

export interface ModelReadyEvent {
  event: "model_ready";
  data: {
    stage: "ocr" | "merge";
    model: string;
    timestamp: string;
  };
}

export interface InferenceStartEvent {
  event: "inference_start";
  data: {
    page_num: number;
    stage: "ocr" | "merge";
    timestamp: string;
  };
}

export interface InferenceCompleteEvent {
  event: "inference_complete";
  data: {
    page_num: number;
    stage: "ocr" | "merge";
    duration_seconds: number;
    timestamp: string;
  };
}

export type StreamResultEvent =
  | OcrPageCompleteEvent
  | MergePageCompleteEvent
  | MergeChunkEvent
  | StageCompleteEvent
  | JobCompleteEvent
  | SystemMessageEvent
  | ModelReadyEvent
  | InferenceStartEvent
  | InferenceCompleteEvent;

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
  cpu_percent?: number;
  memory_percent?: number;
  ram_percent?: number;
  ram_used_gb?: number;
  ram_total_gb?: number;
  gpus?: Array<{
    id: number;
    name?: string;
    memory_used_mb: number;
    memory_total_mb: number;
    memory_percent: number;
    utilization_percent: number;
    temperature_c?: number;
  }>;
  active_jobs?: number;
  queued_jobs?: number;
  queue?: {
    queued?: number;
    processing?: number;
    completed?: number;
    failed?: number;
    cancelled?: number;
  };
  active_model?: {
    model_id?: string;
    load_time_seconds?: number;
    memory_footprint_gb?: number;
  };
}
