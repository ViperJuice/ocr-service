/**
 * API Client for OCR Service
 *
 * Provides type-safe methods for interacting with the OCR Service REST API.
 */

import {
  FileMetadata,
  DirectoryInfo,
  JobSubmitRequest,
  JobCreatedResponse,
  JobStatusResponse,
  JobResult,
  BatchJobStatus,
  BatchResultResponse,
  ProcessingOptions,
  CustomPrompts,
  OutputFormat,
} from "./types";

// ============================================================================
// Configuration
// ============================================================================

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ============================================================================
// Error Handling
// ============================================================================

export class ApiError extends Error {
  constructor(
    message: string,
    public status?: number,
    public detail?: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorDetail = response.statusText;
    try {
      const errorBody = await response.json();
      errorDetail = errorBody.detail || errorBody.message || errorDetail;
    } catch {
      // Ignore JSON parse error
    }
    throw new ApiError(
      `API request failed: ${response.status}`,
      response.status,
      errorDetail
    );
  }
  return response.json();
}

// ============================================================================
// File Upload API
// ============================================================================

/**
 * Upload a single file to the OCR service.
 */
export async function uploadFile(file: File): Promise<FileMetadata> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/api/v1/process/upload`, {
    method: "POST",
    body: formData,
  });

  return handleResponse<FileMetadata>(response);
}

/**
 * Upload a directory of PDF files.
 */
export async function uploadDirectory(
  files: FileList,
  directoryName: string
): Promise<DirectoryInfo> {
  const formData = new FormData();

  // Add all files
  Array.from(files).forEach((file) => {
    formData.append("files", file);
  });

  // Add directory name
  formData.append("directory_name", directoryName);

  const response = await fetch(`${API_BASE_URL}/api/v1/files/directories/upload`, {
    method: "POST",
    body: formData,
  });

  return handleResponse<DirectoryInfo>(response);
}

/**
 * Get file metadata by file ID.
 */
export async function getFileMetadata(fileId: string): Promise<FileMetadata> {
  const response = await fetch(`${API_BASE_URL}/api/v1/files/${fileId}`);
  return handleResponse<FileMetadata>(response);
}

/**
 * Delete a file by file ID.
 */
export async function deleteFile(fileId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/files/${fileId}`, {
    method: "DELETE",
  });
  await handleResponse(response);
}

// ============================================================================
// Job Processing API
// ============================================================================

/**
 * Submit a processing job.
 */
export async function submitJob(request: JobSubmitRequest): Promise<JobCreatedResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/process/jobs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  return handleResponse<JobCreatedResponse>(response);
}

/**
 * Get job status by job ID.
 */
export async function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/process/jobs/${jobId}`);
  return handleResponse<JobStatusResponse>(response);
}

/**
 * Get job result by job ID.
 */
export async function getJobResult(jobId: string): Promise<JobResult> {
  const response = await fetch(`${API_BASE_URL}/api/v1/process/jobs/${jobId}/result`);
  return handleResponse<JobResult>(response);
}

/**
 * Cancel a running job.
 */
export async function cancelJob(jobId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/process/jobs/${jobId}/cancel`, {
    method: "POST",
  });
  await handleResponse(response);
}

/**
 * Download job result as a file.
 */
export async function downloadResult(jobId: string): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}/api/v1/process/jobs/${jobId}/result/download`);
  if (!response.ok) {
    throw new ApiError(`Download failed: ${response.status}`, response.status);
  }
  return response.blob();
}

/**
 * Get DeepSeek-OCR intermediate output for a job.
 */
export async function getOcrOutput(jobId: string): Promise<{
  job_id: string;
  pages: Array<{
    page_num: number;
    text: string;
    processing_time: number;
    metadata: Record<string, any>;
  }>;
  total_pages: number;
}> {
  const response = await fetch(`${API_BASE_URL}/api/v1/process/jobs/${jobId}/ocr-output`);
  return handleResponse(response);
}

/**
 * Get URL for original uploaded file.
 */
export function getOriginalFileUrl(jobId: string): string {
  return `${API_BASE_URL}/api/v1/process/jobs/${jobId}/original`;
}

// ============================================================================
// Batch Processing API
// ============================================================================

export interface BatchJobOptions {
  directory_id: string;
  model?: string;
  prompt_type?: string;
  custom_prompts?: CustomPrompts;
  processing_options?: ProcessingOptions;
  output_format?: OutputFormat;
}

/**
 * Submit a batch processing job for a directory.
 */
export async function submitBatchJob(options: BatchJobOptions): Promise<BatchJobStatus> {
  const response = await fetch(`${API_BASE_URL}/api/v1/batch/process`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      directory_id: options.directory_id,
      model: options.model || "deepseek-ai/deepseek-vl2",
      prompt_type: options.prompt_type || "default",
      custom_prompts: options.custom_prompts,
      processing_options: options.processing_options || {},
      output_format: options.output_format || "markdown",
    }),
  });

  return handleResponse<BatchJobStatus>(response);
}

/**
 * Get batch job status.
 */
export async function getBatchJobStatus(batchJobId: string): Promise<BatchJobStatus> {
  const response = await fetch(`${API_BASE_URL}/api/v1/batch/${batchJobId}/status`);
  return handleResponse<BatchJobStatus>(response);
}

/**
 * Get batch job results.
 */
export async function getBatchResult(batchJobId: string): Promise<BatchResultResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/batch/${batchJobId}/result`);
  return handleResponse<BatchResultResponse>(response);
}

/**
 * Cancel a running batch job.
 */
export async function cancelBatchJob(batchJobId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/batch/${batchJobId}/cancel`, {
    method: "POST",
  });
  await handleResponse(response);
}

// ============================================================================
// System Monitoring API
// ============================================================================

/**
 * Get current system metrics.
 */
export async function getSystemMetrics(): Promise<any> {
  const response = await fetch(`${API_BASE_URL}/api/monitoring/system/current`);
  return handleResponse(response);
}

// ============================================================================
// Server-Sent Events (SSE) API
// ============================================================================

/**
 * Create an EventSource connection for batch progress streaming.
 *
 * This establishes a Server-Sent Events connection to receive real-time
 * progress updates for jobs and batch processing.
 */
export function createBatchProgressStream(): EventSource {
  const url = `${API_BASE_URL}/api/v1/batch/progress/stream`;
  const eventSource = new EventSource(url);

  // Log connection status
  eventSource.addEventListener("connected", (e) => {
    const data = JSON.parse((e as MessageEvent).data);
    console.log("SSE Connected:", data.connection_id);
  });

  eventSource.addEventListener("error", (e) => {
    console.error("SSE Connection error:", e);
  });

  return eventSource;
}

/**
 * Create an EventSource connection for monitoring stream.
 * (For legacy ProgressMonitor component)
 */
export function createMonitoringStream(jobId?: string): EventSource {
  const url = jobId
    ? `${API_BASE_URL}/api/monitoring/stream?job_id=${jobId}`
    : `${API_BASE_URL}/api/monitoring/stream`;
  return new EventSource(url);
}

/**
 * Create an EventSource connection for streaming OCR and merge results.
 *
 * This establishes a Server-Sent Events connection to receive real-time
 * page results as they complete during processing.
 */
export function createResultStream(jobId: string): EventSource {
  const url = `${API_BASE_URL}/api/v1/process/jobs/${jobId}/stream-results`;
  return new EventSource(url);
}

// ============================================================================
// Centralized API Client Object
// ============================================================================

export const apiClient = {
  // File operations
  uploadFile,
  uploadDirectory,
  getFileMetadata,
  deleteFile,

  // Job operations
  submitJob,
  getJobStatus,
  getJobResult,
  cancelJob,
  downloadResult,
  getOcrOutput,
  getOriginalFileUrl,

  // Batch operations
  submitBatchJob,
  getBatchJobStatus,
  getBatchResult,
  cancelBatchJob,

  // System monitoring
  getSystemMetrics,

  // SSE streaming
  createBatchProgressStream,
  createMonitoringStream,
  createResultStream,
};
