# OCR Service - Complete API Reference

> **For Frontend/Web UI Developers**
> This document provides everything you need to build a web interface for the OCR Service API.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Base Configuration](#base-configuration)
3. [Authentication](#authentication)
4. [Complete Endpoint Reference](#complete-endpoint-reference)
   - [Processing Routes](#processing-routes)
   - [Configuration Routes](#configuration-routes)
   - [File Routes](#file-routes)
   - [Monitoring Routes](#monitoring-routes)
   - [Health & Root Routes](#health--root-routes)
5. [Data Models & TypeScript Types](#data-models--typescript-types)
6. [Complete Workflow Examples](#complete-workflow-examples)
7. [Error Handling](#error-handling)
8. [Development Setup](#development-setup)
9. [Limitations & Constraints](#limitations--constraints)

---

## Quick Start

### Starting the Server

```bash
# Development mode (auto-reload)
cd /home/jenner/code/ocr-service
source .venv/bin/activate
OCR_API_RELOAD=true ./scripts/start_api.sh

# Production mode
./scripts/start_api.sh
```

### Access Points

- **API Base URL:** `http://localhost:8000`
- **Interactive Docs (Swagger):** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
- **OpenAPI Schema:** `http://localhost:8000/openapi.json`
- **Health Check:** `http://localhost:8000/health`

### Quick Test

```bash
# Health check
curl http://localhost:8000/health

# Or open in browser
open http://localhost:8000/docs
```

---

## Base Configuration

### Server Settings

| Setting | Default Value | Description |
|---------|---------------|-------------|
| Host | `0.0.0.0` | Server host (all interfaces) |
| Port | `8000` | Server port |
| Workers | `1` | Number of worker processes |
| Reload | `false` | Auto-reload on code changes |

### CORS Configuration

**Enabled by default** for frontend development:

- **Allowed Origins:** `http://localhost:3000` (configurable)
- **Allow Credentials:** `true`
- **Allowed Methods:** All (`GET`, `POST`, `PUT`, `DELETE`, etc.)
- **Allowed Headers:** All

### Upload Constraints

| Constraint | Value |
|------------|-------|
| Max File Size | 50 MB |
| Allowed File Types | PDF, PNG, JPEG, TIFF, BMP |
| File Expiry | 6 hours after upload |
| Concurrent Jobs | 2 maximum (GPU memory limited) |

### API Versioning

- **Current Version:** `v1`
- **API Prefix:** `/api/v1/`
- All endpoints are prefixed with `/api/v1/` except health and root

---

## Authentication

**Current Status:** ❌ No authentication required

- All endpoints are publicly accessible
- No API keys or tokens needed
- No rate limiting implemented
- **For Production:** Implement OAuth2/JWT before deployment

---

## Complete Endpoint Reference

### Processing Routes

Base path: `/api/v1/process`

#### 1. Upload File

**Endpoint:** `POST /api/v1/process/upload`

**Purpose:** Upload a PDF or image file for OCR processing

**Request:**
```http
POST /api/v1/process/upload HTTP/1.1
Host: localhost:8000
Content-Type: multipart/form-data

file: <binary-file-data>
```

**JavaScript Example:**
```javascript
const formData = new FormData();
formData.append('file', fileBlob, 'document.pdf');

const response = await fetch('http://localhost:8000/api/v1/process/upload', {
  method: 'POST',
  body: formData
});

const data = await response.json();
console.log('File ID:', data.file_id);
```

**Response:** `201 Created`
```typescript
{
  file_id: string;          // UUID of uploaded file
  filename: string;         // Original filename
  size_bytes: number;       // File size in bytes
  mime_type: string;        // e.g., "application/pdf"
  uploaded_at: string;      // ISO 8601 timestamp
  expires_at: string;       // ISO 8601 timestamp (upload_time + 6 hours)
  page_count?: number;      // Number of pages (PDF only)
}
```

**Example Response:**
```json
{
  "file_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "filename": "document.pdf",
  "size_bytes": 2048576,
  "mime_type": "application/pdf",
  "uploaded_at": "2025-01-09T12:00:00Z",
  "expires_at": "2025-01-09T18:00:00Z",
  "page_count": 22
}
```

**Errors:**
- `400 Bad Request` - Invalid file type
- `413 Payload Too Large` - File exceeds 50MB

---

#### 2. Submit Processing Job

**Endpoint:** `POST /api/v1/process/jobs`

**Purpose:** Submit a file for OCR processing

**Request:**
```typescript
{
  file_id: string;                    // Required: UUID from upload
  model?: string;                     // Optional: "qwen2-vl-7b" | "deepseek-ocr" (default)
  prompt_type?: string;               // Optional: "markdown" (default) | "ocr" | "merge"
  custom_prompts?: {                  // Optional: Custom prompt templates
    ocr?: string;
    merge?: string;
    format_markdown?: string;
  };
  processing_options?: {              // Optional: Processing configuration
    dpi?: number;                     // 72-600, default: 300
    method?: "auto" | "extract" | "ocr" | "hybrid";  // default: "auto"
    start_page?: number;              // >= 1
    end_page?: number;                // >= start_page
    staged_pipeline?: boolean;        // default: true
    prefer_quality?: boolean;         // default: true
  };
  output_format?: "markdown" | "text" | "json";  // default: "markdown"
}
```

**JavaScript Example:**
```javascript
const response = await fetch('http://localhost:8000/api/v1/process/jobs', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    file_id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
    model: 'qwen2-vl-7b',
    output_format: 'markdown',
    processing_options: {
      dpi: 300,
      prefer_quality: true
    }
  })
});

const { job_id, monitor_url } = await response.json();
```

**Response:** `202 Accepted`
```typescript
{
  job_id: string;              // UUID of created job
  status: "queued";            // Initial status
  created_at: string;          // ISO 8601 timestamp
  file_id: string;             // Reference to uploaded file
  estimated_pages?: number;    // Estimated page count
  monitor_url: string;         // SSE endpoint for real-time updates
}
```

**Example Response:**
```json
{
  "job_id": "987fcdeb-51a2-43f1-9876-123456789abc",
  "status": "queued",
  "created_at": "2025-01-09T12:00:05Z",
  "file_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "estimated_pages": 22,
  "monitor_url": "/api/monitoring/stream?job_id=987fcdeb-51a2-43f1-9876-123456789abc"
}
```

**Errors:**
- `404 Not Found` - File ID doesn't exist
- `422 Validation Error` - Invalid parameters

---

#### 3. Get Job Status

**Endpoint:** `GET /api/v1/process/jobs/{job_id}`

**Purpose:** Check job status and progress

**JavaScript Example:**
```javascript
const response = await fetch(
  `http://localhost:8000/api/v1/process/jobs/${job_id}`
);
const status = await response.json();

console.log(`Status: ${status.status}, Progress: ${status.progress_pct}%`);
```

**Response:** `200 OK`
```typescript
{
  job_id: string;
  status: "queued" | "processing" | "completed" | "failed" | "cancelled";
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  file_id: string;
  filename: string;
  total_pages: number | null;
  pages_completed: number;
  current_stage: "ocr" | "merge" | "format" | null;
  progress_pct: number;              // 0-100
  estimated_remaining_seconds: number | null;
  error: string | null;              // Error message if failed
}
```

**Example Response (Processing):**
```json
{
  "job_id": "987fcdeb-51a2-43f1-9876-123456789abc",
  "status": "processing",
  "created_at": "2025-01-09T12:00:05Z",
  "started_at": "2025-01-09T12:00:10Z",
  "completed_at": null,
  "file_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "filename": "document.pdf",
  "total_pages": 22,
  "pages_completed": 15,
  "current_stage": "ocr",
  "progress_pct": 68.2,
  "estimated_remaining_seconds": 45,
  "error": null
}
```

**Example Response (Completed):**
```json
{
  "job_id": "987fcdeb-51a2-43f1-9876-123456789abc",
  "status": "completed",
  "created_at": "2025-01-09T12:00:05Z",
  "started_at": "2025-01-09T12:00:10Z",
  "completed_at": "2025-01-09T12:04:15Z",
  "file_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "filename": "document.pdf",
  "total_pages": 22,
  "pages_completed": 22,
  "current_stage": null,
  "progress_pct": 100.0,
  "estimated_remaining_seconds": null,
  "error": null
}
```

**Errors:**
- `404 Not Found` - Job ID doesn't exist

---

#### 4. Get Job Result

**Endpoint:** `GET /api/v1/process/jobs/{job_id}/result`

**Purpose:** Retrieve OCR processing results (JSON format)

**JavaScript Example:**
```javascript
const response = await fetch(
  `http://localhost:8000/api/v1/process/jobs/${job_id}/result`
);
const { result } = await response.json();

console.log('Content:', result.content);
console.log('Pages processed:', result.total_pages);
```

**Response:** `200 OK`
```typescript
{
  job_id: string;
  status: "completed";
  result: {
    format: "markdown" | "text" | "json";
    content: string;                 // The OCR output
    total_pages: number;
    processing_time_seconds: number;
    model_used: string;
    metadata: {
      dpi: number;
      method: string;
      pages_processed: number;
      [key: string]: any;
    };
  };
  completed_at: string;
}
```

**Example Response:**
```json
{
  "job_id": "987fcdeb-51a2-43f1-9876-123456789abc",
  "status": "completed",
  "result": {
    "format": "markdown",
    "content": "# Document Title\n\n## Section 1\n\nThis is the extracted text...",
    "total_pages": 22,
    "processing_time_seconds": 245.3,
    "model_used": "qwen2-vl-7b",
    "metadata": {
      "dpi": 300,
      "method": "hybrid",
      "pages_processed": 22
    }
  },
  "completed_at": "2025-01-09T12:04:15Z"
}
```

**Errors:**
- `404 Not Found` - Job doesn't exist
- `409 Conflict` - Job not completed yet (still processing, failed, or cancelled)

---

#### 5. Download Job Result

**Endpoint:** `GET /api/v1/process/jobs/{job_id}/result/download`

**Purpose:** Download result as a file attachment

**JavaScript Example:**
```javascript
// Trigger browser download
window.location.href = `http://localhost:8000/api/v1/process/jobs/${job_id}/result/download`;

// Or fetch and process
const response = await fetch(
  `http://localhost:8000/api/v1/process/jobs/${job_id}/result/download`
);
const blob = await response.blob();
const url = window.URL.createObjectURL(blob);

const a = document.createElement('a');
a.href = url;
a.download = 'result.md';
a.click();
```

**Response:** `200 OK`

**Headers:**
```
Content-Type: text/markdown  (or text/plain, application/json)
Content-Disposition: attachment; filename="document.md"
```

**Errors:**
- `404 Not Found` - Job or result doesn't exist
- `409 Conflict` - Job not completed yet

---

#### 6. Cancel Job

**Endpoint:** `DELETE /api/v1/process/jobs/{job_id}`

**Purpose:** Cancel a running or queued job

**JavaScript Example:**
```javascript
const response = await fetch(
  `http://localhost:8000/api/v1/process/jobs/${job_id}`,
  { method: 'DELETE' }
);
const data = await response.json();
console.log(data.message);
```

**Response:** `200 OK`
```typescript
{
  job_id: string;
  status: "cancelled";
  message: string;
}
```

**Example Response:**
```json
{
  "job_id": "987fcdeb-51a2-43f1-9876-123456789abc",
  "status": "cancelled",
  "message": "Job cancelled successfully"
}
```

**Errors:**
- `404 Not Found` - Job doesn't exist
- `409 Conflict` - Job already completed/failed (cannot cancel)

---

### Configuration Routes

Base path: `/api/v1/config`

#### 7. List Available Models

**Endpoint:** `GET /api/v1/config/models`

**Purpose:** Get list of available OCR models

**JavaScript Example:**
```javascript
const response = await fetch('http://localhost:8000/api/v1/config/models');
const { models } = await response.json();

// Display models in dropdown
models.forEach(model => {
  console.log(`${model.name}: ${model.description}`);
});
```

**Response:** `200 OK`
```typescript
{
  models: Array<{
    model_id: string;
    name: string;
    description: string;
    capabilities: string[];          // ["ocr", "markdown", "merge", "structured"]
    estimated_memory_gb: number;
    default: boolean;
  }>;
}
```

**Example Response:**
```json
{
  "models": [
    {
      "model_id": "qwen3-vl-8b",
      "name": "Qwen3-VL 8B",
      "description": "Highest quality, best for production documents",
      "capabilities": ["ocr", "markdown", "merge", "structured"],
      "estimated_memory_gb": 18.0,
      "default": false
    },
    {
      "model_id": "deepseek-ocr",
      "name": "DeepSeek-OCR",
      "description": "Specialized OCR model, faster processing",
      "capabilities": ["ocr"],
      "estimated_memory_gb": 15.2,
      "default": true
    }
  ]
}
```

---

#### 8. List Prompt Types

**Endpoint:** `GET /api/v1/config/prompts`

**Purpose:** Get available prompt types and their templates

**JavaScript Example:**
```javascript
const response = await fetch('http://localhost:8000/api/v1/config/prompts');
const { prompt_types } = await response.json();
```

**Response:** `200 OK`
```typescript
{
  prompt_types: Array<{
    type: string;
    description: string;
    default_template: string;
    variables: string[];             // Required template variables
  }>;
}
```

**Example Response:**
```json
{
  "prompt_types": [
    {
      "type": "ocr",
      "description": "OCR extraction prompt for processing images",
      "default_template": "Extract all text from the following image: <image>...",
      "variables": ["image"]
    },
    {
      "type": "merge",
      "description": "Merge embedded and OCR text intelligently",
      "default_template": "Merge the following texts: Embedded: {embedded_text}, OCR: {ocr_text}",
      "variables": ["embedded_text", "ocr_text"]
    }
  ]
}
```

---

#### 9. Validate Custom Prompt

**Endpoint:** `POST /api/v1/config/prompts/validate`

**Purpose:** Validate a custom prompt template before use

**Request:**
```typescript
{
  prompt_type: string;              // "ocr" | "merge" | "format_markdown"
  template: string;                 // Custom prompt template
  model?: string;                   // Optional: model to validate against
}
```

**JavaScript Example:**
```javascript
const response = await fetch('http://localhost:8000/api/v1/config/prompts/validate', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    prompt_type: 'merge',
    template: 'Combine: {embedded_text} and {ocr_text}',
    model: 'qwen2-vl-7b'
  })
});

const validation = await response.json();
if (!validation.valid) {
  console.error('Invalid prompt:', validation.warnings);
}
```

**Response:** `200 OK`
```typescript
{
  valid: boolean;
  warnings: string[];                // Warning messages
  required_variables: string[];      // Expected variables for this type
  found_variables: string[];         // Variables found in template
}
```

**Example Response (Valid):**
```json
{
  "valid": true,
  "warnings": [],
  "required_variables": ["embedded_text", "ocr_text"],
  "found_variables": ["embedded_text", "ocr_text"]
}
```

**Example Response (Invalid):**
```json
{
  "valid": false,
  "warnings": ["Missing required variable: ocr_text"],
  "required_variables": ["embedded_text", "ocr_text"],
  "found_variables": ["embedded_text"]
}
```

---

#### 10. Get System Settings

**Endpoint:** `GET /api/v1/config/settings`

**Purpose:** Retrieve system configuration and defaults

**JavaScript Example:**
```javascript
const response = await fetch('http://localhost:8000/api/v1/config/settings');
const settings = await response.json();

console.log('Max upload size:', settings.max_upload_size_mb, 'MB');
console.log('File expiry:', settings.temp_file_expiry_hours, 'hours');
```

**Response:** `200 OK`
```typescript
{
  max_upload_size_mb: number;
  default_output_format: string;
  default_dpi: number;
  default_model: string;
  max_batch_size: number;
  enable_staged_pipeline: boolean;
  temp_file_expiry_hours: number;
}
```

**Example Response:**
```json
{
  "max_upload_size_mb": 50,
  "default_output_format": "markdown",
  "default_dpi": 300,
  "default_model": "deepseek-ocr",
  "max_batch_size": 10,
  "enable_staged_pipeline": true,
  "temp_file_expiry_hours": 6
}
```

---

### File Routes

Base path: `/api/v1/files`

#### 11. Get File Metadata

**Endpoint:** `GET /api/v1/files/{file_id}`

**Purpose:** Retrieve metadata for an uploaded file

**JavaScript Example:**
```javascript
const response = await fetch(
  `http://localhost:8000/api/v1/files/${file_id}`
);
const metadata = await response.json();

console.log(`${metadata.filename}: ${metadata.size_bytes} bytes`);
```

**Response:** `200 OK`
```typescript
{
  file_id: string;
  filename: string;
  size_bytes: number;
  mime_type: string;
  uploaded_at: string;
  expires_at: string;
  page_count?: number;               // PDF only
}
```

**Errors:**
- `404 Not Found` - File doesn't exist or has expired

---

#### 12. Delete File

**Endpoint:** `DELETE /api/v1/files/{file_id}`

**Purpose:** Delete an uploaded file before expiry

**JavaScript Example:**
```javascript
const response = await fetch(
  `http://localhost:8000/api/v1/files/${file_id}`,
  { method: 'DELETE' }
);
const { deleted } = await response.json();
```

**Response:** `200 OK`
```typescript
{
  file_id: string;
  deleted: boolean;
}
```

**Errors:**
- `404 Not Found` - File doesn't exist

---

### Monitoring Routes

Base path: `/api/monitoring`

#### 13. Real-Time Progress Stream (SSE)

**Endpoint:** `GET /api/monitoring/stream`

**Purpose:** Server-Sent Events stream for real-time job progress

**Query Parameters:**
- `job_id` (optional): Filter by specific job
- `interval` (optional): Update interval in seconds (1-30, default: 2)

**JavaScript Example:**
```javascript
const eventSource = new EventSource(
  `http://localhost:8000/api/monitoring/stream?job_id=${job_id}&interval=2`
);

eventSource.onmessage = (event) => {
  const metrics = JSON.parse(event.data);

  // Update UI with progress
  updateProgressBar(metrics.overall_progress_pct);
  updateCurrentStage(metrics.active_stage);
  updatePageCounter(metrics.stage_page, metrics.stage_total_pages);
};

eventSource.onerror = (error) => {
  console.error('SSE connection error:', error);
  eventSource.close();
};

// Close when done
eventSource.close();
```

**Response:** `200 OK` (text/event-stream)

**SSE Message Format:**
```typescript
{
  timestamp: string;                 // ISO 8601
  job_id: string;
  active_stage: "ocr" | "merge" | "format";
  stage_page: number;                // Current page in this stage
  stage_total_pages: number;         // Total pages in this stage
  overall_progress_pct: number;      // 0-100
}
```

**Example SSE Events:**
```
data: {"timestamp":"2025-01-09T12:00:15Z","job_id":"987fcdeb...","active_stage":"ocr","stage_page":3,"stage_total_pages":22,"overall_progress_pct":6.8}

data: {"timestamp":"2025-01-09T12:00:17Z","job_id":"987fcdeb...","active_stage":"ocr","stage_page":5,"stage_total_pages":22,"overall_progress_pct":13.6}

data: {"timestamp":"2025-01-09T12:02:30Z","job_id":"987fcdeb...","active_stage":"merge","stage_page":10,"stage_total_pages":22,"overall_progress_pct":61.4}
```

---

#### 14. Get Current Metrics

**Endpoint:** `GET /api/monitoring/current`

**Purpose:** Get most recent metrics snapshot

**Query Parameters:**
- `job_id` (optional): Filter by job ID

**JavaScript Example:**
```javascript
const response = await fetch(
  `http://localhost:8000/api/monitoring/current?job_id=${job_id}`
);
const metrics = await response.json();
```

**Response:** `200 OK`

Returns the latest metrics object (same format as SSE message).

**Errors:**
- `404 Not Found` - No metrics available

---

#### 15. Get Metrics History

**Endpoint:** `GET /api/monitoring/history`

**Purpose:** Retrieve historical metrics

**Query Parameters:**
- `job_id` (optional): Filter by job ID
- `minutes` (optional): Time window (1-1440, default: 60)
- `event_type` (optional): Filter by event type

**JavaScript Example:**
```javascript
const response = await fetch(
  `http://localhost:8000/api/monitoring/history?job_id=${job_id}&minutes=30`
);
const history = await response.json();

// Plot metrics over time
history.forEach(metric => {
  plotPoint(metric.timestamp, metric.overall_progress_pct);
});
```

**Response:** `200 OK`

Array of metrics objects.

---

#### 16. List Active Jobs

**Endpoint:** `GET /api/monitoring/jobs`

**Purpose:** Get list of currently active job IDs

**JavaScript Example:**
```javascript
const response = await fetch('http://localhost:8000/api/monitoring/jobs');
const { jobs } = await response.json();

console.log(`${jobs.length} active jobs`);
```

**Response:** `200 OK`
```typescript
{
  jobs: string[];                    // Array of job IDs
}
```

---

#### 17. Get Job Summary

**Endpoint:** `GET /api/monitoring/jobs/{job_id}`

**Purpose:** Get detailed job summary with stage transitions

**JavaScript Example:**
```javascript
const response = await fetch(
  `http://localhost:8000/api/monitoring/jobs/${job_id}`
);
const summary = await response.json();
```

**Response:** `200 OK`

Detailed job summary including stage transitions and timings.

**Errors:**
- `404 Not Found` - Job not found

---

#### 18. Get Page Completion Events

**Endpoint:** `GET /api/monitoring/pages`

**Purpose:** Retrieve page completion events

**Query Parameters:**
- `job_id` (optional): Filter by job ID
- `stage` (optional): Filter by "ocr" or "merge"

**JavaScript Example:**
```javascript
const response = await fetch(
  `http://localhost:8000/api/monitoring/pages?job_id=${job_id}&stage=ocr`
);
const pages = await response.json();
```

**Response:** `200 OK`

Array of page completion events.

---

#### 19. Monitoring Health Check

**Endpoint:** `GET /api/monitoring/health`

**Purpose:** Health check for monitoring service

**Response:** `200 OK`
```json
{
  "status": "ok",
  "service": "monitoring"
}
```

---

### Health & Root Routes

#### 20. Health Check

**Endpoint:** `GET /health`

**Purpose:** API health check

**JavaScript Example:**
```javascript
const response = await fetch('http://localhost:8000/health');
const { status } = await response.json();

if (status !== 'healthy') {
  console.error('API is unhealthy!');
}
```

**Response:** `200 OK`
```json
{
  "status": "healthy",
  "service": "ocr-service"
}
```

---

#### 21. API Root

**Endpoint:** `GET /`

**Purpose:** Get API information

**Response:** `200 OK`
```json
{
  "service": "OCR Service API",
  "version": "0.1.0",
  "docs": "/docs",
  "health": "/health"
}
```

---

#### 22. OpenAPI Schema

**Endpoint:** `GET /openapi.json`

**Purpose:** Get OpenAPI 3.0 specification

**Response:** `200 OK`

Complete OpenAPI JSON schema for the API.

---

## Data Models & TypeScript Types

### Complete Type Definitions

```typescript
// ===== ENUMS =====

type JobStatus =
  | "queued"       // Job created, waiting to start
  | "processing"   // Job actively running
  | "completed"    // Job finished successfully
  | "failed"       // Job encountered an error
  | "cancelled";   // Job was cancelled

type OutputFormat =
  | "markdown"     // Markdown formatted text
  | "text"         // Plain text
  | "json";        // Structured JSON

type ProcessingMethod =
  | "auto"         // Automatically choose best method
  | "extract"      // Extract embedded text only (fastest)
  | "ocr"          // OCR only (for scanned documents)
  | "hybrid";      // AI-powered merge of extracted + OCR (highest quality)

type ProcessingStage =
  | "ocr"          // OCR extraction
  | "merge"        // Text merging
  | "format";      // Output formatting

// ===== REQUEST MODELS =====

interface ProcessingOptions {
  dpi?: number;                      // 72-600, default: 300
  method?: ProcessingMethod;         // default: "auto"
  start_page?: number;               // >= 1
  end_page?: number;                 // >= start_page
  staged_pipeline?: boolean;         // default: true
  prefer_quality?: boolean;          // default: true
}

interface CustomPrompts {
  ocr?: string;
  merge?: string;
  format_markdown?: string;
}

interface JobSubmitRequest {
  file_id: string;                   // Required
  model?: string;                    // Optional, default: "deepseek-ocr"
  prompt_type?: string;              // Optional, default: "markdown"
  custom_prompts?: CustomPrompts;    // Optional
  processing_options?: ProcessingOptions;  // Optional
  output_format?: OutputFormat;      // Optional, default: "markdown"
}

interface PromptValidationRequest {
  prompt_type: string;               // "ocr" | "merge" | "format_markdown"
  template: string;
  model?: string;
}

// ===== RESPONSE MODELS =====

interface FileMetadata {
  file_id: string;
  filename: string;
  size_bytes: number;
  mime_type: string;
  uploaded_at: string;               // ISO 8601
  expires_at: string;                // ISO 8601
  page_count?: number;               // PDF only
}

interface JobCreatedResponse {
  job_id: string;
  status: "queued";
  created_at: string;
  file_id: string;
  estimated_pages?: number;
  monitor_url: string;
}

interface JobStatus {
  job_id: string;
  status: JobStatus;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  file_id: string;
  filename: string;
  total_pages: number | null;
  pages_completed: number;
  current_stage: ProcessingStage | null;
  progress_pct: number;              // 0-100
  estimated_remaining_seconds: number | null;
  error: string | null;
}

interface JobResult {
  job_id: string;
  status: "completed";
  result: {
    format: OutputFormat;
    content: string;
    total_pages: number;
    processing_time_seconds: number;
    model_used: string;
    metadata: {
      dpi: number;
      method: string;
      pages_processed: number;
      [key: string]: any;
    };
  };
  completed_at: string;
}

interface ModelInfo {
  model_id: string;
  name: string;
  description: string;
  capabilities: string[];
  estimated_memory_gb: number;
  default: boolean;
}

interface ModelsResponse {
  models: ModelInfo[];
}

interface PromptType {
  type: string;
  description: string;
  default_template: string;
  variables: string[];
}

interface PromptsResponse {
  prompt_types: PromptType[];
}

interface PromptValidationResponse {
  valid: boolean;
  warnings: string[];
  required_variables: string[];
  found_variables: string[];
}

interface SystemSettings {
  max_upload_size_mb: number;
  default_output_format: string;
  default_dpi: number;
  default_model: string;
  max_batch_size: number;
  enable_staged_pipeline: boolean;
  temp_file_expiry_hours: number;
}

interface MonitoringMetrics {
  timestamp: string;
  job_id: string;
  active_stage: ProcessingStage;
  stage_page: number;
  stage_total_pages: number;
  overall_progress_pct: number;
}

interface ErrorResponse {
  error: string;
  detail?: string | any[];
  code?: string;
}
```

---

## Complete Workflow Examples

### 1. Basic Upload → Process → Download Workflow

```typescript
async function processDocument(file: File): Promise<string> {
  try {
    // Step 1: Upload file
    const formData = new FormData();
    formData.append('file', file);

    const uploadResponse = await fetch('http://localhost:8000/api/v1/process/upload', {
      method: 'POST',
      body: formData
    });

    if (!uploadResponse.ok) {
      throw new Error(`Upload failed: ${uploadResponse.statusText}`);
    }

    const { file_id } = await uploadResponse.json();
    console.log('✓ File uploaded:', file_id);

    // Step 2: Submit processing job
    const jobResponse = await fetch('http://localhost:8000/api/v1/process/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_id,
        model: 'qwen2-vl-7b',
        output_format: 'markdown',
        processing_options: {
          dpi: 300,
          prefer_quality: true
        }
      })
    });

    const { job_id } = await jobResponse.json();
    console.log('✓ Job submitted:', job_id);

    // Step 3: Poll for completion
    const finalStatus = await pollJobCompletion(job_id);

    if (finalStatus.status === 'failed') {
      throw new Error(finalStatus.error || 'Job failed');
    }

    console.log('✓ Job completed');

    // Step 4: Get result
    const resultResponse = await fetch(
      `http://localhost:8000/api/v1/process/jobs/${job_id}/result`
    );
    const { result } = await resultResponse.json();

    console.log('✓ Result retrieved');
    return result.content;

  } catch (error) {
    console.error('Error processing document:', error);
    throw error;
  }
}

async function pollJobCompletion(
  job_id: string,
  intervalMs: number = 2000,
  maxAttempts: number = 300
): Promise<JobStatus> {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const response = await fetch(
      `http://localhost:8000/api/v1/process/jobs/${job_id}`
    );
    const status: JobStatus = await response.json();

    console.log(`Progress: ${status.progress_pct.toFixed(1)}%`);

    if (status.status === 'completed' || status.status === 'failed') {
      return status;
    }

    await new Promise(resolve => setTimeout(resolve, intervalMs));
  }

  throw new Error('Job timed out');
}
```

---

### 2. Real-Time Progress with SSE

```typescript
interface ProgressCallbacks {
  onProgress: (progress: number, stage: string) => void;
  onComplete: () => void;
  onError: (error: string) => void;
}

function monitorJobProgress(
  job_id: string,
  callbacks: ProgressCallbacks
): () => void {
  const eventSource = new EventSource(
    `http://localhost:8000/api/monitoring/stream?job_id=${job_id}&interval=2`
  );

  eventSource.onmessage = (event) => {
    const metrics: MonitoringMetrics = JSON.parse(event.data);

    callbacks.onProgress(
      metrics.overall_progress_pct,
      metrics.active_stage
    );

    // Check if complete
    if (metrics.overall_progress_pct >= 100) {
      eventSource.close();
      callbacks.onComplete();
    }
  };

  eventSource.onerror = (error) => {
    console.error('SSE error:', error);
    eventSource.close();
    callbacks.onError('Connection lost');
  };

  // Return cleanup function
  return () => eventSource.close();
}

// Usage
const cleanup = monitorJobProgress(job_id, {
  onProgress: (progress, stage) => {
    updateProgressBar(progress);
    updateStageLabel(stage);
  },
  onComplete: () => {
    console.log('Job completed!');
    fetchResult(job_id);
  },
  onError: (error) => {
    console.error('Monitoring error:', error);
    showErrorMessage(error);
  }
});

// Cleanup when component unmounts
onComponentUnmount(() => cleanup());
```

---

### 3. Custom Prompts for Specialized Documents

```typescript
async function processLegalDocument(file: File): Promise<string> {
  // Upload file
  const formData = new FormData();
  formData.append('file', file);
  const uploadResponse = await fetch('http://localhost:8000/api/v1/process/upload', {
    method: 'POST',
    body: formData
  });
  const { file_id } = await uploadResponse.json();

  // Submit with custom prompts
  const jobResponse = await fetch('http://localhost:8000/api/v1/process/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      file_id,
      model: 'qwen2-vl-7b',
      output_format: 'markdown',
      custom_prompts: {
        merge: `You are a legal document specialist. Carefully merge these texts
                while preserving legal terminology, citations, and formatting:

                Embedded text: {embedded_text}
                OCR text: {ocr_text}

                Ensure all section numbers, citations, and legal references are
                accurately preserved.`
      }
    })
  });

  const { job_id } = await jobResponse.json();

  // Wait for completion and get result
  const finalStatus = await pollJobCompletion(job_id);
  const resultResponse = await fetch(
    `http://localhost:8000/api/v1/process/jobs/${job_id}/result`
  );
  const { result } = await resultResponse.json();

  return result.content;
}
```

---

### 4. React Hook Example

```typescript
import { useState, useEffect } from 'react';

interface UseOcrJobResult {
  status: JobStatus | null;
  progress: number;
  result: string | null;
  error: string | null;
  submit: (file: File) => Promise<void>;
  cancel: () => Promise<void>;
}

function useOcrJob(): UseOcrJobResult {
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Monitor progress with SSE
  useEffect(() => {
    if (!jobId) return;

    const eventSource = new EventSource(
      `http://localhost:8000/api/monitoring/stream?job_id=${jobId}&interval=2`
    );

    eventSource.onmessage = (event) => {
      const metrics = JSON.parse(event.data);
      setProgress(metrics.overall_progress_pct);

      if (metrics.overall_progress_pct >= 100) {
        eventSource.close();
        fetchResult(jobId);
      }
    };

    eventSource.onerror = () => {
      eventSource.close();
      setError('Connection lost');
    };

    return () => eventSource.close();
  }, [jobId]);

  async function submit(file: File) {
    try {
      setError(null);
      setProgress(0);

      // Upload
      const formData = new FormData();
      formData.append('file', file);
      const uploadRes = await fetch('http://localhost:8000/api/v1/process/upload', {
        method: 'POST',
        body: formData
      });
      const { file_id } = await uploadRes.json();

      // Submit job
      const jobRes = await fetch('http://localhost:8000/api/v1/process/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_id,
          output_format: 'markdown'
        })
      });
      const { job_id } = await jobRes.json();

      setJobId(job_id);
    } catch (err) {
      setError(err.message);
    }
  }

  async function fetchResult(jobId: string) {
    try {
      const res = await fetch(
        `http://localhost:8000/api/v1/process/jobs/${jobId}/result`
      );
      const data = await res.json();
      setStatus('completed');
      setResult(data.result.content);
    } catch (err) {
      setError(err.message);
    }
  }

  async function cancel() {
    if (!jobId) return;
    await fetch(`http://localhost:8000/api/v1/process/jobs/${jobId}`, {
      method: 'DELETE'
    });
    setStatus('cancelled');
  }

  return { status, progress, result, error, submit, cancel };
}

// Usage in component
function OcrUploadComponent() {
  const { status, progress, result, error, submit, cancel } = useOcrJob();

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      await submit(file);
    }
  };

  return (
    <div>
      <input type="file" accept=".pdf" onChange={handleFileChange} />
      {status === 'processing' && (
        <div>
          <progress value={progress} max={100} />
          <button onClick={cancel}>Cancel</button>
        </div>
      )}
      {result && <pre>{result}</pre>}
      {error && <div className="error">{error}</div>}
    </div>
  );
}
```

---

## Error Handling

### Standard Error Response Format

All API errors return JSON in this format:

```typescript
{
  error: string;                     // Human-readable error message
  detail?: string | any[];           // Additional details (optional)
  code?: string;                     // Error code (optional)
}
```

### HTTP Status Codes

| Code | Meaning | When It Occurs |
|------|---------|----------------|
| 200 | OK | Successful GET/DELETE |
| 201 | Created | File uploaded successfully |
| 202 | Accepted | Job submitted successfully |
| 400 | Bad Request | Invalid file type, malformed request |
| 404 | Not Found | Resource doesn't exist or expired |
| 409 | Conflict | Operation not allowed in current state |
| 413 | Payload Too Large | File exceeds 50MB |
| 422 | Validation Error | Invalid request parameters |
| 500 | Internal Server Error | Server-side error |

### Common Error Scenarios

#### 1. Invalid File Type (400)

```json
{
  "error": "Invalid file type: text/plain. Allowed types: PDF, PNG, JPEG, TIFF, BMP",
  "code": "HTTP_400"
}
```

**How to Handle:**
```typescript
if (!response.ok) {
  const error = await response.json();
  if (response.status === 400 && error.error.includes('Invalid file type')) {
    alert('Please upload a PDF or image file');
  }
}
```

---

#### 2. File Too Large (413)

```json
{
  "error": "File size exceeds maximum allowed size of 50MB",
  "code": "HTTP_413"
}
```

**How to Handle:**
```typescript
// Pre-check file size before upload
if (file.size > 50 * 1024 * 1024) {
  alert('File must be less than 50MB');
  return;
}
```

---

#### 3. Resource Not Found (404)

```json
{
  "error": "Job not found: invalid-job-id",
  "code": "HTTP_404"
}
```

**How to Handle:**
```typescript
if (response.status === 404) {
  console.error('Job may have expired or been deleted');
  // Redirect to upload page
}
```

---

#### 4. Job Not Ready (409)

```json
{
  "error": "Job not completed yet. Current status: processing",
  "code": "HTTP_409"
}
```

**How to Handle:**
```typescript
if (response.status === 409) {
  console.log('Job still processing, try again later');
  // Continue polling
}
```

---

#### 5. Validation Error (422)

```json
{
  "error": "Validation error",
  "detail": [
    {
      "loc": ["body", "processing_options", "end_page"],
      "msg": "end_page must be >= start_page",
      "type": "value_error"
    }
  ],
  "code": "VALIDATION_ERROR"
}
```

**How to Handle:**
```typescript
if (response.status === 422) {
  const error = await response.json();
  error.detail.forEach(err => {
    console.error(`${err.loc.join('.')}: ${err.msg}`);
  });
}
```

---

### Comprehensive Error Handler

```typescript
async function apiRequest<T>(
  url: string,
  options?: RequestInit
): Promise<T> {
  try {
    const response = await fetch(url, options);

    if (!response.ok) {
      const error = await response.json().catch(() => ({
        error: response.statusText
      }));

      switch (response.status) {
        case 400:
          throw new Error(`Bad Request: ${error.error}`);
        case 404:
          throw new Error(`Not Found: ${error.error}`);
        case 409:
          throw new Error(`Conflict: ${error.error}`);
        case 413:
          throw new Error('File too large (max 50MB)');
        case 422:
          const validationErrors = error.detail
            .map(e => `${e.loc.join('.')}: ${e.msg}`)
            .join(', ');
          throw new Error(`Validation Error: ${validationErrors}`);
        case 500:
          throw new Error('Server error. Please try again later.');
        default:
          throw new Error(error.error || 'Unknown error');
      }
    }

    return await response.json();
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error('Network error. Check your connection.');
    }
    throw error;
  }
}

// Usage
try {
  const result = await apiRequest<JobCreatedResponse>(
    'http://localhost:8000/api/v1/process/jobs',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(jobRequest)
    }
  );
  console.log('Job created:', result.job_id);
} catch (error) {
  console.error('Failed to create job:', error.message);
  showUserError(error.message);
}
```

---

## Development Setup

### Environment Variables

Create a `.env` file in the project root:

```bash
# API Server
OCR_API_HOST=0.0.0.0
OCR_API_PORT=8000
OCR_API_WORKERS=1
OCR_API_RELOAD=false

# CORS
OCR_ENABLE_CORS=true
OCR_CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]

# Upload Limits
OCR_MAX_UPLOAD_SIZE_MB=50

# File Storage
OCR_TEMP_FILE_EXPIRY_HOURS=6

# Default Settings
OCR_DEFAULT_MODEL=deepseek-ocr
OCR_DEFAULT_OUTPUT_FORMAT=markdown
```

### Starting the Server

```bash
# Navigate to project
cd /home/jenner/code/ocr-service

# Activate virtual environment
source .venv/bin/activate

# Development mode (recommended for frontend dev)
OCR_API_RELOAD=true ./scripts/start_api.sh

# Production mode
./scripts/start_api.sh

# Custom port
OCR_API_PORT=8080 ./scripts/start_api.sh
```

### Testing the API

```bash
# Health check
curl http://localhost:8000/health

# Upload a file
curl -X POST http://localhost:8000/api/v1/process/upload \
  -F "file=@test.pdf"

# Get OpenAPI schema
curl http://localhost:8000/openapi.json | jq '.'
```

### Using Swagger UI

1. Start the server
2. Open `http://localhost:8000/docs` in your browser
3. Try out endpoints interactively
4. View request/response schemas
5. Download OpenAPI spec

---

## Limitations & Constraints

### Important Limitations to Know

#### 1. **No Job Persistence**
- ⚠️ Jobs are stored in memory only
- Server restart = all jobs lost
- **Implication:** Don't rely on job IDs across server restarts

#### 2. **File Expiry**
- ⚠️ Uploaded files auto-delete after 6 hours
- Cannot retrieve results after file expires
- **Implication:** Download results promptly

#### 3. **Concurrent Job Limit**
- ⚠️ Maximum 2 jobs can run simultaneously
- GPU memory constraint
- **Implication:** Queue management needed for multiple users

#### 4. **No Authentication**
- ⚠️ API is completely open
- No user isolation
- **Implication:** Not production-ready without auth layer

#### 5. **No Webhooks**
- ⚠️ No callback notifications on completion
- Must poll or use SSE
- **Implication:** Client must actively monitor

#### 6. **No Batch Processing**
- ⚠️ One file per job
- Cannot process multiple files in single request
- **Implication:** Loop through files client-side

#### 7. **No Rate Limiting**
- ⚠️ Unlimited requests allowed
- Can overwhelm server
- **Implication:** Implement client-side throttling

#### 8. **SSE Connection Limits**
- ⚠️ Browser limit: ~6 SSE connections per domain
- **Implication:** Close connections when done

### Resource Limits

| Resource | Limit | Reason |
|----------|-------|--------|
| File Size | 50 MB | Memory/bandwidth |
| Concurrent Jobs | 2 | GPU memory |
| File Expiry | 6 hours | Disk space |
| Page Range | No limit | Processing time may be long |
| Concurrent SSE | ~6 per browser | Browser limitation |

### Best Practices

1. **Always close SSE connections** when done monitoring
2. **Check file size before upload** to avoid errors
3. **Implement retry logic** for transient errors
4. **Cache results client-side** before file expiry
5. **Show clear error messages** to users
6. **Implement upload progress** for large files
7. **Add timeouts** to API requests
8. **Handle network errors** gracefully

---

## Additional Resources

- **Interactive API Docs:** http://localhost:8000/docs
- **OpenAPI Specification:** http://localhost:8000/openapi.json
- **GitHub Repository:** (your repo URL)
- **Issue Tracker:** (your issue tracker URL)

---

## Support & Questions

For questions about this API:

1. Check the interactive docs at `/docs`
2. Review the OpenAPI schema at `/openapi.json`
3. Refer to code examples in this document
4. File an issue in the repository

---

**Last Updated:** January 2025
**API Version:** 1.0.0
**Document Version:** 1.0.0
