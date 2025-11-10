# Inline Progress + Batch Directory Processing Specification

**Version:** 1.0
**Date:** 2025-11-09
**Status:** Planning / Pre-Implementation

---

## Executive Summary

This specification outlines the implementation of inline progress tracking and batch directory processing for the OCR service. The system will support three processing modes:
1. Single page processing with simple progress indication
2. Multi-page document processing with page-by-page progress
3. Batch directory processing with hierarchical progress (batch → document → page)

### Scope
- **21 files to modify** (11 backend, 10 frontend)
- **10 new files to create** (6 backend, 4 frontend)
- **0 new dependencies required** (using existing packages)
- **Backend:** FastAPI with SSE streaming, in-memory state management
- **Frontend:** Next.js 16.0.1, React with TypeScript, inline progress messages
- **Package Management:** uv for Python backend
- **Production Ready:** All imports and setup designed for easy production deployment

---

## Table of Contents

1. [Backend Architecture](#backend-architecture)
2. [Frontend Architecture](#frontend-architecture)
3. [Data Structures](#data-structures)
4. [Files to Modify](#files-to-modify)
5. [Files to Create](#files-to-create)
6. [Implementation Phases](#implementation-phases)
7. [Testing Strategy](#testing-strategy)
8. [SSE Stream Enhancements](#sse-stream-enhancements)

---

## Backend Architecture

### Core Components

#### 1. BatchManager (New)
**Location:** `/src/api/services/batch_manager.py`

```python
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
import threading
import logging

@dataclass
class BatchJob:
    """Batch job containing multiple document jobs."""
    batch_job_id: str
    directory_id: str
    file_ids: List[str]
    document_jobs: Dict[str, 'Job']  # job_id -> Job
    total_documents: int
    documents_completed: int
    overall_progress_pct: float
    status: 'BatchJobStatus'
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    cancel_requested: bool = False

class BatchJobStatus(Enum):
    """Batch job status enum."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class BatchManager:
    """Manage batch job lifecycle and processing."""

    def __init__(
        self,
        processing_directory: str,
        output_directory: str,
        max_concurrent_batches: int = 1
    ):
        """Initialize batch manager."""
        pass

    def create_batch_job(
        self,
        directory_id: str,
        file_ids: List[str],
        model: str,
        prompt_type: str,
        custom_prompts: Optional[Dict[str, str]],
        processing_options: Dict[str, Any],
        output_format: str
    ) -> BatchJob:
        """Create a new batch job for directory processing."""
        pass

    def start_batch_job(
        self,
        batch_job_id: str,
        file_manager: 'FileManager',
        job_manager: 'JobManager',
        prompt_manager: 'PromptManager',
        model_manager: 'ModelManager',
        progress_emitter: 'ProgressEmitter'
    ) -> None:
        """Start processing a batch job asynchronously."""
        pass

    def _process_batch_async(
        self,
        batch: BatchJob,
        file_manager,
        job_manager,
        prompt_manager,
        model_manager,
        progress_emitter
    ) -> None:
        """Process batch job asynchronously (runs in background thread)."""
        pass

    def get_batch_job(self, batch_job_id: str) -> BatchJob:
        """Get batch job by ID."""
        pass

    def cancel_batch_job(self, batch_job_id: str) -> bool:
        """Cancel a running batch job."""
        pass

    def get_batch_result(self, batch_job_id: str) -> Dict[str, Any]:
        """Get batch job results (all document results)."""
        pass
```

#### 2. ProgressEmitter (New)
**Location:** `/src/api/services/progress_emitter.py`

```python
from typing import Optional, Dict, Any
import asyncio
import json
import logging

class ProgressEmitter:
    """Centralized SSE progress emission."""

    def __init__(self):
        """Initialize progress emitter with active connections."""
        self.connections: Dict[str, asyncio.Queue] = {}
        self.lock = asyncio.Lock()

    async def register_connection(self, connection_id: str) -> asyncio.Queue:
        """Register a new SSE connection."""
        pass

    async def unregister_connection(self, connection_id: str) -> None:
        """Unregister an SSE connection."""
        pass

    async def emit_job_progress(
        self,
        job_id: str,
        progress_pct: float,
        current_stage: str,
        pages_completed: int,
        total_pages: Optional[int] = None
    ) -> None:
        """Emit progress update for a single job."""
        pass

    async def emit_batch_progress(
        self,
        batch_job_id: str,
        overall_progress_pct: float,
        documents_completed: int,
        total_documents: int,
        current_document_id: Optional[str] = None,
        current_document_progress: Optional[Dict[str, Any]] = None
    ) -> None:
        """Emit progress update for a batch job."""
        pass

    async def emit_error(
        self,
        job_id: str,
        error_message: str,
        is_batch: bool = False
    ) -> None:
        """Emit error event."""
        pass

    async def emit_completion(
        self,
        job_id: str,
        is_batch: bool = False
    ) -> None:
        """Emit completion event."""
        pass
```

#### 3. Enhanced JobManager
**Location:** `/src/api/services/job_manager.py` (Modify existing)

**New Methods:**
```python
def set_progress_callback(
    self,
    job_id: str,
    callback: Callable[[float, int, str], None]
) -> None:
    """Set a progress callback for real-time updates."""
    pass

def _emit_progress(
    self,
    job_id: str,
    progress_pct: float,
    pages_completed: int,
    stage: str
) -> None:
    """Internal method to emit progress via callback."""
    pass
```

**Modified Methods:**
- `_process_job_async()` - Add progress callback invocations during processing
- `start_job()` - Accept optional progress callback parameter

#### 4. Enhanced FileManager
**Location:** `/src/api/services/file_manager.py` (Modify existing)

**New Methods:**
```python
def upload_directory(
    self,
    files: List[UploadFile],
    directory_name: str
) -> Tuple[str, List[str]]:
    """
    Upload a directory of PDF files.

    Returns:
        Tuple of (directory_id, list of file_ids)
    """
    pass

def get_directory_files(self, directory_id: str) -> List[Dict[str, Any]]:
    """Get all files in a directory."""
    pass

def validate_pdf_batch(self, files: List[UploadFile]) -> List[str]:
    """Validate that all files are valid PDFs. Returns error messages."""
    pass
```

**New Data Structures:**
```python
@dataclass
class Directory:
    """Directory metadata."""
    directory_id: str
    name: str
    file_ids: List[str]
    total_size: int
    uploaded_at: datetime
```

---

## Frontend Architecture

### Core Components

#### 1. InlineProgress Component (New)
**Location:** `/web/components/InlineProgress.tsx`

```typescript
interface InlineProgressProps {
  progress_pct: number;
  content: string;
  isBatch?: boolean;
  currentPage?: number;
  totalPages?: number;
  documentsCompleted?: number;
  totalDocuments?: number;
  currentDocument?: string;
  stage?: string;
}

export function InlineProgress({
  progress_pct,
  content,
  isBatch = false,
  currentPage,
  totalPages,
  documentsCompleted,
  totalDocuments,
  currentDocument,
  stage
}: InlineProgressProps): JSX.Element {
  // Renders inline progress bar with contextual information
  // Single page: Simple spinner or minimal progress
  // Multi-page: Page X of Y progress bar
  // Batch: Hierarchical display (batch → document → page)
}
```

#### 2. BatchProgressCard Component (New)
**Location:** `/web/components/BatchProgressCard.tsx`

```typescript
interface BatchProgressCardProps {
  batchJobId: string;
  totalDocuments: number;
  documentsCompleted: number;
  currentDocument: DocumentProgress | null;
  overallProgressPct: number;
}

export function BatchProgressCard({
  batchJobId,
  totalDocuments,
  documentsCompleted,
  currentDocument,
  overallProgressPct
}: BatchProgressCardProps): JSX.Element {
  // Renders hierarchical batch progress:
  // - Overall batch progress bar
  // - Current document name and progress
  // - Current page within current document
}
```

#### 3. DocumentProgressItem Component (New)
**Location:** `/web/components/DocumentProgressItem.tsx`

```typescript
interface DocumentProgressItemProps {
  filename: string;
  progress_pct: number;
  currentPage?: number;
  totalPages?: number;
  status: 'queued' | 'processing' | 'completed' | 'failed';
}

export function DocumentProgressItem({
  filename,
  progress_pct,
  currentPage,
  totalPages,
  status
}: DocumentProgressItemProps): JSX.Element {
  // Renders individual document progress within batch
}
```

#### 4. Enhanced ChatMessage Component
**Location:** `/web/components/ChatMessage.tsx` (Modify existing)

**New Props:**
```typescript
interface ChatMessageProps {
  message: ChatMessage;
  inlineProgress?: InlineProgressData | null; // NEW
}

interface InlineProgressData {
  type: 'single' | 'multi-page' | 'batch';
  progress_pct: number;
  content: string;
  // ... other progress fields
}
```

**Changes:**
- Conditionally render `<InlineProgress>` component below message content
- Subscribe to progress updates via SSE for active jobs
- Update progress state in real-time

#### 5. DirectoryUploadZone Component (New)
**Location:** `/web/components/DirectoryUploadZone.tsx`

```typescript
interface DirectoryUploadZoneProps {
  onDirectorySelect: (files: FileList) => void;
  isUploading: boolean;
  uploadedDirectory?: DirectoryInfo;
  onClear: () => void;
}

export function DirectoryUploadZone({
  onDirectorySelect,
  isUploading,
  uploadedDirectory,
  onClear
}: DirectoryUploadZoneProps): JSX.Element {
  // Renders directory upload zone with:
  // - Drag-and-drop for folders
  // - File list preview
  // - Validation (all files must be PDFs)
}
```

---

## Data Structures

### Backend Data Structures

#### Batch Request Model
**Location:** `/src/api/models/requests.py` (Extend existing)

```python
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any

class BatchProcessRequest(BaseModel):
    """Request to process a batch of documents."""
    directory_id: str = Field(..., description="Directory ID containing PDFs")
    model: str = Field(default="deepseek-ai/deepseek-vl2", description="Model to use")
    prompt_type: str = Field(default="default", description="Prompt type")
    custom_prompts: Optional[Dict[str, str]] = Field(None, description="Custom prompts")
    processing_options: Dict[str, Any] = Field(
        default_factory=dict,
        description="Processing options (dpi, prefer_quality, etc.)"
    )
    output_format: str = Field(default="markdown", description="Output format")
```

#### Batch Response Model
**Location:** `/src/api/models/responses.py` (Extend existing)

```python
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

class BatchJobResponse(BaseModel):
    """Response for batch job creation/status."""
    batch_job_id: str
    directory_id: str
    total_documents: int
    documents_completed: int
    overall_progress_pct: float
    status: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

class BatchResultResponse(BaseModel):
    """Response containing all batch results."""
    batch_job_id: str
    total_documents: int
    documents_completed: int
    results: List[Dict[str, Any]]  # List of document results
    overall_processing_time_seconds: float
```

#### SSE Event Types
**Location:** `/src/api/routes/monitoring.py` (Extend existing)

```python
# New SSE event types:

# 1. Batch Progress Event
{
    "event": "batch_progress",
    "data": {
        "batch_job_id": "uuid",
        "overall_progress_pct": 45.5,
        "documents_completed": 3,
        "total_documents": 10,
        "current_document": {
            "job_id": "uuid",
            "filename": "document3.pdf",
            "progress_pct": 60.0,
            "current_page": 6,
            "total_pages": 10,
            "stage": "ocr"
        }
    }
}

# 2. Document Progress Event (within batch)
{
    "event": "document_progress",
    "data": {
        "batch_job_id": "uuid",
        "job_id": "uuid",
        "filename": "document3.pdf",
        "progress_pct": 60.0,
        "current_page": 6,
        "total_pages": 10,
        "stage": "ocr"
    }
}

# 3. Single Job Progress Event (existing, enhanced)
{
    "event": "job_progress",
    "data": {
        "job_id": "uuid",
        "progress_pct": 75.0,
        "current_page": 8,
        "total_pages": 10,
        "stage": "merge",
        "pages_completed": 8
    }
}
```

### Frontend Data Structures

#### Type Definitions
**Location:** `/web/lib/types.ts` (Extend existing)

```typescript
// Batch-related types
export interface BatchJobStatus {
  batch_job_id: string;
  directory_id: string;
  total_documents: number;
  documents_completed: number;
  overall_progress_pct: number;
  status: 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled';
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
  status: 'queued' | 'processing' | 'completed' | 'failed';
}

export interface BatchProgress {
  batch_job_id: string;
  overall_progress_pct: number;
  documents_completed: number;
  total_documents: number;
  current_document: DocumentProgress | null;
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
  }>;
}

// Inline progress types
export interface InlineProgressData {
  type: 'single' | 'multi-page' | 'batch';
  progress_pct: number;
  content: string;
  currentPage?: number;
  totalPages?: number;
  documentsCompleted?: number;
  totalDocuments?: number;
  currentDocument?: string;
  stage?: string;
}

// Extended ChatMessage to support inline progress
export interface ChatMessage {
  id: string;
  role: 'user' | 'system';
  content: string;
  timestamp: number;
  metadata?: any;
  inlineProgress?: InlineProgressData; // NEW
}
```

---

## Files to Modify

### Backend Files (11 files)

#### 1. `/src/api/routes/files.py`
**Purpose:** Add directory upload endpoint

**New Endpoints:**
```python
@router.post("/directories/upload", response_model=DirectoryUploadResponse)
async def upload_directory(
    files: List[UploadFile] = File(...),
    directory_name: str = Form(...),
    file_manager: FileManager = Depends(get_file_manager)
) -> DirectoryUploadResponse:
    """Upload a directory of PDF files."""
    pass
```

#### 2. `/src/api/routes/jobs.py`
**Purpose:** Extend for batch support awareness

**Modified Endpoints:**
- `GET /jobs/{job_id}/status` - Add `parent_batch_id` field to response
- `GET /jobs/{job_id}/result` - Include batch context if applicable

#### 3. `/src/api/routes/monitoring.py`
**Purpose:** Enhance SSE with batch events

**Modified:**
```python
@router.get("/stream")
async def stream_events(request: Request) -> StreamingResponse:
    """
    SSE stream for real-time monitoring.

    Enhanced to support:
    - batch_progress events
    - document_progress events (within batch)
    - job_progress events (enhanced with batch context)
    """
    pass
```

#### 4. `/src/api/services/job_manager.py`
**Purpose:** Add progress callbacks, batch context

**New Methods:**
```python
def set_progress_callback(self, job_id: str, callback: Callable) -> None:
    """Set progress callback for real-time updates."""
    pass

def _emit_progress(self, job_id: str, progress_pct: float, pages_completed: int, stage: str) -> None:
    """Emit progress via callback."""
    pass
```

**Modified Methods:**
- `_process_job_async()` - Add progress callback invocations at key points
- `Job` dataclass - Add `parent_batch_id: Optional[str]` field

#### 5. `/src/api/services/file_manager.py`
**Purpose:** Add directory handling

**New Methods:**
```python
def upload_directory(self, files: List[UploadFile], directory_name: str) -> Tuple[str, List[str]]:
    """Upload directory of PDFs."""
    pass

def get_directory_files(self, directory_id: str) -> List[Dict[str, Any]]:
    """Get all files in a directory."""
    pass

def validate_pdf_batch(self, files: List[UploadFile]) -> List[str]:
    """Validate PDF batch."""
    pass
```

**New Data Structures:**
```python
@dataclass
class Directory:
    directory_id: str
    name: str
    file_ids: List[str]
    total_size: int
    uploaded_at: datetime
```

**New State:**
```python
self.directories: Dict[str, Directory] = {}
```

#### 6. `/src/preprocessing/staged_pipeline.py`
**Purpose:** Add progress callbacks

**Modified:**
```python
class StagedPipelineProcessor:
    def __init__(
        self,
        # ... existing params
        progress_callback: Optional[Callable[[float, int, str], None]] = None  # NEW
    ):
        self.progress_callback = progress_callback

    def _emit_progress(self, progress_pct: float, pages_completed: int, stage: str) -> None:
        """Emit progress if callback is set."""
        if self.progress_callback:
            self.progress_callback(progress_pct, pages_completed, stage)

    def process_pdf(self, ...):
        # Add progress emission at key points:
        # - After each page OCR
        # - After merge stage
        # - After format stage
        pass
```

#### 7. `/src/api/models/requests.py`
**Purpose:** Add batch request models

**New Models:**
```python
class BatchProcessRequest(BaseModel):
    directory_id: str
    model: str = "deepseek-ai/deepseek-vl2"
    prompt_type: str = "default"
    custom_prompts: Optional[Dict[str, str]] = None
    processing_options: Dict[str, Any] = Field(default_factory=dict)
    output_format: str = "markdown"
```

#### 8. `/src/api/models/responses.py`
**Purpose:** Add batch response models

**New Models:**
```python
class BatchJobResponse(BaseModel):
    batch_job_id: str
    directory_id: str
    total_documents: int
    documents_completed: int
    overall_progress_pct: float
    status: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

class BatchResultResponse(BaseModel):
    batch_job_id: str
    total_documents: int
    documents_completed: int
    results: List[Dict[str, Any]]
    overall_processing_time_seconds: float

class DirectoryUploadResponse(BaseModel):
    directory_id: str
    name: str
    file_count: int
    total_size: int
    files: List[Dict[str, Any]]
```

#### 9. `/src/api/main.py`
**Purpose:** Register new routes

**Modified:**
```python
from .routes import batch

# Register batch routes
app.include_router(batch.router, prefix="/api/batch", tags=["batch"])
```

#### 10. `/src/utils/system_monitor.py`
**Purpose:** Extend monitoring for batch context

**Modified:**
```python
class SystemMonitor:
    def get_metrics(self) -> Dict[str, Any]:
        # Add batch-specific metrics:
        # - active_batch_jobs
        # - total_batch_documents_processing
        pass
```

#### 11. `/src/api/dependencies.py`
**Purpose:** Add batch manager dependency

**New:**
```python
def get_batch_manager() -> BatchManager:
    """Get batch manager instance."""
    return batch_manager

def get_progress_emitter() -> ProgressEmitter:
    """Get progress emitter instance."""
    return progress_emitter
```

---

### Frontend Files (10 files)

#### 1. `/web/lib/types.ts`
**Purpose:** Add batch types

**New Types:**
```typescript
export interface BatchJobStatus { /* ... */ }
export interface DocumentProgress { /* ... */ }
export interface BatchProgress { /* ... */ }
export interface DirectoryInfo { /* ... */ }
export interface InlineProgressData { /* ... */ }
```

**Modified Types:**
```typescript
export interface ChatMessage {
  // ... existing fields
  inlineProgress?: InlineProgressData; // NEW
}
```

#### 2. `/web/lib/api-client.ts`
**Purpose:** Add batch methods

**New Methods:**
```typescript
export async function uploadDirectory(
  files: FileList,
  directoryName: string
): Promise<DirectoryInfo> { /* ... */ }

export async function submitBatchJob(
  directoryId: string,
  options: BatchProcessOptions
): Promise<BatchJobStatus> { /* ... */ }

export async function getBatchJobStatus(
  batchJobId: string
): Promise<BatchJobStatus> { /* ... */ }

export async function getBatchResult(
  batchJobId: string
): Promise<BatchResultResponse> { /* ... */ }

export async function cancelBatchJob(
  batchJobId: string
): Promise<void> { /* ... */ }
```

#### 3. `/web/components/ChatMessage.tsx`
**Purpose:** Add inline progress rendering

**Modified:**
```typescript
interface ChatMessageProps {
  message: ChatMessage;
  inlineProgress?: InlineProgressData | null; // NEW
}

export function ChatMessage({ message, inlineProgress }: ChatMessageProps) {
  return (
    <div className="...">
      {/* Existing message content */}
      <p>{message.content}</p>

      {/* NEW: Inline progress rendering */}
      {inlineProgress && (
        <InlineProgress
          progress_pct={inlineProgress.progress_pct}
          content={inlineProgress.content}
          isBatch={inlineProgress.type === 'batch'}
          currentPage={inlineProgress.currentPage}
          totalPages={inlineProgress.totalPages}
          documentsCompleted={inlineProgress.documentsCompleted}
          totalDocuments={inlineProgress.totalDocuments}
          currentDocument={inlineProgress.currentDocument}
          stage={inlineProgress.stage}
        />
      )}
    </div>
  );
}
```

#### 4. `/web/components/MessageList.tsx`
**Purpose:** Support progress updates

**Modified:**
```typescript
export function MessageList({ messages }: MessageListProps) {
  const [progressMap, setProgressMap] = useState<Map<string, InlineProgressData>>(new Map());

  // Subscribe to SSE for progress updates
  useEffect(() => {
    const eventSource = new EventSource('/api/monitoring/stream');

    eventSource.addEventListener('job_progress', (e) => {
      const data = JSON.parse(e.data);
      // Update progressMap for corresponding message
    });

    eventSource.addEventListener('batch_progress', (e) => {
      const data = JSON.parse(e.data);
      // Update progressMap for corresponding message
    });

    return () => eventSource.close();
  }, []);

  return (
    <div className="...">
      {messages.map((msg) => (
        <ChatMessage
          key={msg.id}
          message={msg}
          inlineProgress={progressMap.get(msg.id)}
        />
      ))}
    </div>
  );
}
```

#### 5. `/web/components/FileDropZone.tsx`
**Purpose:** Add directory upload mode

**Modified:**
```typescript
interface FileDropZoneProps {
  onFileSelect: (file: File) => void;
  onDirectorySelect?: (files: FileList) => void; // NEW
  uploadedFile?: FileInfo;
  uploadedDirectory?: DirectoryInfo; // NEW
  isUploading: boolean;
  onClear: () => void;
  mode?: 'single' | 'directory'; // NEW
}

export function FileDropZone({
  onFileSelect,
  onDirectorySelect,
  uploadedFile,
  uploadedDirectory,
  isUploading,
  onClear,
  mode = 'single'
}: FileDropZoneProps) {
  // Add directory drop handling
  // Show file list for directories
  // Validate all files are PDFs
}
```

#### 6. `/web/app/page.tsx`
**Purpose:** Integrate batch mode

**Modified:**
```typescript
export default function Home() {
  const [uploadMode, setUploadMode] = useState<'single' | 'directory'>('single');
  const [currentDirectory, setCurrentDirectory] = useState<DirectoryInfo | null>(null);
  const [currentBatchJob, setCurrentBatchJob] = useState<BatchJobStatus | null>(null);

  // Add directory upload handler
  const handleDirectorySelect = useCallback(async (files: FileList) => {
    // Upload directory
    // Store directory info
  }, []);

  // Add batch job submission handler
  const handleBatchCommand = useCallback(async (userInput: string) => {
    // Parse command for batch processing
    // Submit batch job
    // Track batch progress
  }, []);

  // Extend handleCommand to support batch
  const handleCommand = useCallback(async (userInput: string) => {
    if (uploadMode === 'directory') {
      await handleBatchCommand(userInput);
    } else {
      // Existing single document logic
    }
  }, [uploadMode, handleBatchCommand]);
}
```

#### 7. `/web/hooks/useOcrJob.ts`
**Purpose:** Add batch support

**Modified:**
```typescript
export function useOcrJob() {
  const [currentBatchJob, setCurrentBatchJob] = useState<BatchJobStatus | null>(null);
  const [batchResult, setBatchResult] = useState<BatchResultResponse | null>(null);

  const uploadDirectory = useCallback(async (files: FileList, name: string) => {
    // Upload directory API call
  }, []);

  const submitBatchJob = useCallback(async (options: BatchJobOptions) => {
    // Submit batch job API call
  }, []);

  const fetchBatchResult = useCallback(async (batchJobId: string) => {
    // Fetch batch result API call
  }, []);

  return {
    // ... existing fields
    currentBatchJob,
    batchResult,
    uploadDirectory,
    submitBatchJob,
    fetchBatchResult,
  };
}
```

#### 8. `/web/lib/command-parser.ts`
**Purpose:** Add batch commands

**Modified:**
```typescript
export function parseCommand(input: string): ParsedCommand {
  const normalized = input.toLowerCase().trim();

  // NEW: Parse directory/batch commands
  if (normalized.match(/parse (the )?(whole |entire )?directory/)) {
    return {
      type: "parse_directory",
      params: {},
      originalText: input,
    };
  }

  // ... existing command parsing
}

export function getSuggestions(input: string): string[] {
  const allSuggestions = [
    // ... existing suggestions
    "Parse the whole directory", // NEW
    "Parse directory", // NEW
  ];

  // ... existing logic
}
```

#### 9. `/web/components/ProgressMonitor.tsx`
**Purpose:** Mark as deprecated (keep for backwards compatibility)

**Modified:**
```typescript
/**
 * @deprecated Use inline progress messages instead (InlineProgress component)
 * Kept for backwards compatibility only
 */
export function ProgressMonitor({ ... }) {
  // Existing implementation unchanged
  // Display deprecation warning in console
  console.warn('ProgressMonitor is deprecated. Use InlineProgress instead.');
}
```

#### 10. `/web/styles/globals.css`
**Purpose:** Add progress styles

**New Styles:**
```css
/* Inline progress bar styles */
.inline-progress-container {
  margin-top: 0.75rem;
  padding: 0.75rem;
  background-color: rgba(59, 130, 246, 0.1);
  border-left: 3px solid rgb(59, 130, 246);
  border-radius: 0.375rem;
}

.inline-progress-bar {
  height: 0.5rem;
  background-color: rgba(59, 130, 246, 0.2);
  border-radius: 0.25rem;
  overflow: hidden;
}

.inline-progress-fill {
  height: 100%;
  background-color: rgb(59, 130, 246);
  transition: width 0.3s ease;
}

.batch-progress-card {
  margin-top: 1rem;
  padding: 1rem;
  background-color: rgba(147, 51, 234, 0.1);
  border: 1px solid rgba(147, 51, 234, 0.3);
  border-radius: 0.5rem;
}

.document-progress-item {
  padding: 0.5rem;
  margin-top: 0.5rem;
  background-color: rgba(255, 255, 255, 0.05);
  border-radius: 0.375rem;
}
```

---

## Files to Create

### Backend Files (6 files)

#### 1. `/src/api/services/batch_manager.py`
**Purpose:** Batch job orchestration
**Key Classes:** `BatchManager`, `BatchJob`, `BatchJobStatus`
**Dependencies:** `JobManager`, `FileManager`, `ProgressEmitter`

#### 2. `/src/api/routes/batch.py`
**Purpose:** Batch-specific API endpoints
**Endpoints:**
- `POST /batch/process` - Submit batch job
- `GET /batch/{batch_job_id}/status` - Get batch status
- `GET /batch/{batch_job_id}/result` - Get batch results
- `POST /batch/{batch_job_id}/cancel` - Cancel batch job

#### 3. `/src/api/models/batch.py`
**Purpose:** Batch data structures
**Models:** `BatchJob`, `BatchJobStatus`, `BatchProgress`

#### 4. `/src/api/services/progress_emitter.py`
**Purpose:** Centralized SSE emission
**Key Class:** `ProgressEmitter`
**Methods:** `emit_job_progress`, `emit_batch_progress`, `emit_error`, `emit_completion`

#### 5. `/src/api/schemas/batch_schemas.py`
**Purpose:** Validation schemas for batch operations
**Schemas:** `BatchProcessRequestSchema`, `BatchJobResponseSchema`, `BatchResultResponseSchema`

#### 6. `/tests/api/test_batch_processing.py`
**Purpose:** Comprehensive batch processing tests
**Test Cases:**
- Directory upload validation
- Batch job creation
- Batch processing lifecycle
- Progress emission
- Error handling
- Cancellation

---

### Frontend Files (4 files)

#### 1. `/web/components/InlineProgress.tsx`
**Purpose:** Inline progress component for chat messages
**Props:** `InlineProgressProps`
**Features:**
- Simple spinner for single pages
- Progress bar for multi-page documents
- Hierarchical display for batch jobs

#### 2. `/web/components/BatchProgressCard.tsx`
**Purpose:** Batch progress display
**Props:** `BatchProgressCardProps`
**Features:**
- Overall batch progress bar
- Current document indicator
- Document list with individual progress

#### 3. `/web/components/DirectoryUploadZone.tsx`
**Purpose:** Multi-file upload component
**Props:** `DirectoryUploadZoneProps`
**Features:**
- Drag-and-drop for folders
- File list preview
- PDF validation

#### 4. `/web/hooks/useBatchJob.ts`
**Purpose:** Batch job lifecycle management
**Returns:** Batch job state and control functions
**Features:**
- Directory upload
- Batch job submission
- Real-time status updates via SSE
- Result fetching

#### 5. `/web/lib/batch-utils.ts`
**Purpose:** Batch utility functions
**Functions:**
- `calculateBatchProgress()`
- `formatBatchStatus()`
- `validatePdfBatch()`
- `groupResultsByDocument()`

#### 6. `/web/components/DocumentProgressItem.tsx`
**Purpose:** Individual document progress within batch
**Props:** `DocumentProgressItemProps`
**Features:**
- Document name and status
- Page progress bar
- Completion indicator

---

## Implementation Phases

### Phase 1: Backend Core (2-3 days)
**Goal:** Implement core batch processing infrastructure

**Tasks:**
1. Create `BatchManager` class with job orchestration logic
2. Create `ProgressEmitter` class for centralized SSE emission
3. Create batch data models (`BatchJob`, `BatchJobStatus`, etc.)
4. Extend `FileManager` with directory upload support
5. Add progress callbacks to `JobManager`
6. Write unit tests for `BatchManager` and `ProgressEmitter`

**Deliverables:**
- `/src/api/services/batch_manager.py`
- `/src/api/services/progress_emitter.py`
- `/src/api/models/batch.py`
- Updated `/src/api/services/file_manager.py`
- Updated `/src/api/services/job_manager.py`
- `/tests/api/test_batch_processing.py`

**Validation:**
- Unit tests pass
- Can create batch jobs programmatically
- Progress callbacks work correctly

---

### Phase 2: Backend API (2-3 days)
**Goal:** Expose batch functionality via REST API

**Tasks:**
1. Create batch route handlers (`/api/batch/*`)
2. Create directory upload endpoint (`/api/files/directories/upload`)
3. Enhance SSE monitoring route with batch events
4. Add batch request/response schemas
5. Update API dependencies for batch manager
6. Integration testing for batch endpoints

**Deliverables:**
- `/src/api/routes/batch.py`
- Updated `/src/api/routes/files.py`
- Updated `/src/api/routes/monitoring.py`
- `/src/api/schemas/batch_schemas.py`
- Updated `/src/api/dependencies.py`
- Updated `/src/api/main.py`

**Validation:**
- Can upload directory via API
- Can submit batch job via API
- SSE stream emits batch progress events
- Integration tests pass

---

### Phase 3: Frontend Core (2-3 days)
**Goal:** Implement frontend batch data structures and hooks

**Tasks:**
1. Add batch types to `types.ts`
2. Add batch API methods to `api-client.ts`
3. Create `useBatchJob` hook
4. Create batch utility functions (`batch-utils.ts`)
5. Write unit tests for hooks and utilities

**Deliverables:**
- Updated `/web/lib/types.ts`
- Updated `/web/lib/api-client.ts`
- `/web/hooks/useBatchJob.ts`
- `/web/lib/batch-utils.ts`

**Validation:**
- TypeScript compilation succeeds
- Hook tests pass
- Can call batch API methods

---

### Phase 4: Frontend UI Components (3-4 days)
**Goal:** Build UI components for inline progress and batch display

**Tasks:**
1. Create `InlineProgress` component
2. Create `BatchProgressCard` component
3. Create `DocumentProgressItem` component
4. Create `DirectoryUploadZone` component
5. Update `ChatMessage` to render inline progress
6. Update `MessageList` to subscribe to SSE and update progress
7. Update `FileDropZone` to support directory mode
8. Add progress styles to `globals.css`
9. Component testing (visual and functional)

**Deliverables:**
- `/web/components/InlineProgress.tsx`
- `/web/components/BatchProgressCard.tsx`
- `/web/components/DocumentProgressItem.tsx`
- `/web/components/DirectoryUploadZone.tsx`
- Updated `/web/components/ChatMessage.tsx`
- Updated `/web/components/MessageList.tsx`
- Updated `/web/components/FileDropZone.tsx`
- Updated `/web/styles/globals.css`

**Validation:**
- Components render correctly
- Progress updates animate smoothly
- Batch progress displays hierarchically
- Directory upload works

---

### Phase 5: Integration (2-3 days)
**Goal:** Wire up batch mode in main application

**Tasks:**
1. Update `page.tsx` to support batch mode
2. Update `useOcrJob` hook to support batch operations
3. Update `command-parser.ts` to parse batch commands
4. Implement SSE subscription in `MessageList`
5. Connect directory upload to batch job submission
6. End-to-end testing

**Deliverables:**
- Updated `/web/app/page.tsx`
- Updated `/web/hooks/useOcrJob.ts`
- Updated `/web/lib/command-parser.ts`
- End-to-end test scenarios

**Validation:**
- Can upload directory
- Can submit batch job
- Progress updates appear inline in chat
- Batch results display correctly
- All three modes work (single page, multi-page, batch)

---

### Phase 6: Testing & Polish (2-3 days)
**Goal:** Comprehensive testing and UX refinement

**Tasks:**
1. End-to-end testing of all scenarios:
   - Single page processing
   - Multi-page processing
   - Batch directory processing
2. Error handling testing:
   - Invalid PDFs in batch
   - Cancellation during batch processing
   - Network errors
3. Performance testing:
   - Large batches (50+ documents)
   - Concurrent batch jobs
4. UX polish:
   - Loading states
   - Error messages
   - Progress animations
   - Accessibility (ARIA labels)
5. Documentation:
   - API documentation
   - User guide
   - Developer notes

**Deliverables:**
- Comprehensive test suite
- Performance benchmarks
- Polished UI/UX
- Documentation

**Validation:**
- All tests pass
- Performance meets requirements
- UX is smooth and intuitive
- Documentation is complete

---

## Testing Strategy

### Backend Testing

#### Unit Tests
**Location:** `/tests/api/`

**Test Files:**
1. `test_batch_manager.py`
   - `test_create_batch_job()`
   - `test_start_batch_job()`
   - `test_batch_progress_tracking()`
   - `test_cancel_batch_job()`
   - `test_batch_error_handling()`

2. `test_progress_emitter.py`
   - `test_register_connection()`
   - `test_emit_job_progress()`
   - `test_emit_batch_progress()`
   - `test_multiple_connections()`

3. `test_file_manager_batch.py`
   - `test_upload_directory()`
   - `test_validate_pdf_batch()`
   - `test_invalid_files_in_batch()`

#### Integration Tests
**Location:** `/tests/integration/`

**Test Files:**
1. `test_batch_api.py`
   - `test_directory_upload_endpoint()`
   - `test_batch_job_submission()`
   - `test_batch_status_endpoint()`
   - `test_batch_result_endpoint()`
   - `test_batch_sse_stream()`

2. `test_batch_workflow.py`
   - `test_full_batch_processing_workflow()`
   - `test_batch_with_page_ranges()`
   - `test_concurrent_batch_jobs()`

---

### Frontend Testing

#### Component Tests
**Location:** `/web/__tests__/components/`

**Test Files:**
1. `InlineProgress.test.tsx`
   - Single page mode rendering
   - Multi-page mode rendering
   - Batch mode rendering
   - Progress bar animations

2. `BatchProgressCard.test.tsx`
   - Hierarchical progress display
   - Current document highlighting
   - Progress calculations

3. `DirectoryUploadZone.test.tsx`
   - File selection
   - Drag-and-drop
   - PDF validation
   - Error states

#### Hook Tests
**Location:** `/web/__tests__/hooks/`

**Test Files:**
1. `useBatchJob.test.ts`
   - Directory upload
   - Batch job submission
   - Status updates
   - Result fetching

#### Integration Tests
**Location:** `/web/__tests__/integration/`

**Test Files:**
1. `batch-workflow.test.tsx`
   - Full batch processing flow
   - SSE progress updates
   - Error handling
   - Cancellation

---

### End-to-End Testing

**Tool:** Playwright or Cypress

**Test Scenarios:**
1. **Single Page Processing**
   - Upload single PDF
   - Parse single page
   - View inline progress
   - View results

2. **Multi-Page Processing**
   - Upload multi-page PDF
   - Parse page range
   - View page-by-page progress
   - View results

3. **Batch Processing**
   - Upload directory
   - Parse entire directory
   - View hierarchical progress
   - View batch results

4. **Error Scenarios**
   - Upload invalid files
   - Cancel during processing
   - Network errors
   - Backend errors

---

## SSE Stream Enhancements

### Current SSE Events (Existing)
```python
# System metrics
{
    "event": "metrics",
    "data": { ... }
}

# Job progress (basic)
{
    "event": "job_progress",
    "data": {
        "job_id": "...",
        "status": "processing",
        "progress": 0.5
    }
}
```

### New SSE Events

#### 1. Enhanced Job Progress
```python
{
    "event": "job_progress",
    "data": {
        "job_id": "uuid",
        "status": "processing",
        "progress_pct": 75.0,
        "current_page": 8,
        "total_pages": 10,
        "stage": "merge",  # ocr | merge | format
        "pages_completed": 8,
        "parent_batch_id": "uuid | null"  # NEW: Link to parent batch if applicable
    }
}
```

#### 2. Batch Progress Event
```python
{
    "event": "batch_progress",
    "data": {
        "batch_job_id": "uuid",
        "status": "processing",
        "overall_progress_pct": 45.5,
        "documents_completed": 3,
        "total_documents": 10,
        "current_document": {
            "job_id": "uuid",
            "filename": "document3.pdf",
            "progress_pct": 60.0,
            "current_page": 6,
            "total_pages": 10,
            "stage": "ocr"
        }
    }
}
```

#### 3. Document Progress Event (Within Batch)
```python
{
    "event": "document_progress",
    "data": {
        "batch_job_id": "uuid",
        "job_id": "uuid",
        "filename": "document3.pdf",
        "progress_pct": 60.0,
        "current_page": 6,
        "total_pages": 10,
        "stage": "ocr",
        "status": "processing"
    }
}
```

#### 4. Batch Completion Event
```python
{
    "event": "batch_complete",
    "data": {
        "batch_job_id": "uuid",
        "total_documents": 10,
        "documents_completed": 10,
        "documents_failed": 0,
        "overall_processing_time_seconds": 245.5
    }
}
```

#### 5. Error Event (Enhanced)
```python
{
    "event": "error",
    "data": {
        "job_id": "uuid | null",
        "batch_job_id": "uuid | null",
        "error_message": "...",
        "error_type": "processing_error | validation_error | ...",
        "recoverable": true | false
    }
}
```

---

## Production Deployment Considerations

### Backend Dependencies (No Changes Required)
All required packages already in `pyproject.toml`:
- `fastapi`
- `uvicorn`
- `pydantic`
- `python-multipart` (for file uploads)

**Package Management:** Use `uv` for all installations:
```bash
uv pip install -r requirements.txt  # or uv sync
```

### Frontend Dependencies (No Changes Required)
All required packages already in `package.json`:
- `next` (16.0.1)
- `react`
- `typescript`
- `@tanstack/react-query`
- `lucide-react`

### Environment Configuration
No new environment variables required. Existing configuration sufficient:
- `UPLOAD_DIR`
- `OUTPUT_DIR`
- Backend/frontend ports

### Deployment Checklist
1. Backend:
   - Ensure `uv` is installed
   - Run `uv sync` to install dependencies
   - Set up upload/output directories
   - Configure CORS for frontend origin
   - Start with `uvicorn src.api.main:app --host 0.0.0.0 --port 8000`

2. Frontend:
   - Run `npm install`
   - Build: `npm run build`
   - Start: `npm start` (production) or `npm run dev` (development)

3. Monitoring:
   - SSE connections should be monitored for connection limits
   - File cleanup policies for old uploads/results
   - Batch job cleanup (automatic via `cleanup_old_jobs`)

---

## Database Considerations

**Current Architecture:** In-memory state management (no database)

**Implications:**
- Job state lost on server restart
- No persistent job history
- Suitable for development and small-scale production
- For large-scale production, consider:
  - PostgreSQL for job/batch state persistence
  - Redis for SSE connection management
  - Object storage (S3) for uploaded files/results

**Future Enhancement (Out of Scope):**
If database persistence is required, add:
- SQLAlchemy models for `Job`, `BatchJob`, `File`, `Directory`
- Database migrations (Alembic)
- Update managers to use database instead of in-memory dicts

---

## API Endpoint Summary

### Existing Endpoints (No Changes)
- `POST /api/files/upload`
- `POST /api/jobs/process`
- `GET /api/jobs/{job_id}/status`
- `GET /api/jobs/{job_id}/result`
- `POST /api/jobs/{job_id}/cancel`
- `GET /api/monitoring/stream` (enhanced)
- `GET /api/monitoring/metrics`

### New Endpoints (Batch)
- `POST /api/files/directories/upload` - Upload directory of PDFs
- `POST /api/batch/process` - Submit batch job
- `GET /api/batch/{batch_job_id}/status` - Get batch status
- `GET /api/batch/{batch_job_id}/result` - Get all batch results
- `POST /api/batch/{batch_job_id}/cancel` - Cancel batch job

---

## Success Criteria

### Functional Requirements
- [x] Inline progress messages appear in chat below system messages
- [x] Single page processing shows simple progress indicator
- [x] Multi-page processing shows page-by-page progress
- [x] Batch directory processing shows hierarchical progress (batch → document → page)
- [x] Backend accepts single documents, directories, and page ranges
- [x] SSE streams real-time progress for all modes
- [x] Error handling for invalid files, cancellation, network issues

### Non-Functional Requirements
- [x] No new dependencies required
- [x] Production-ready setup with `uv` package manager
- [x] TypeScript type safety throughout frontend
- [x] Responsive UI with smooth animations
- [x] Accessible (ARIA labels, keyboard navigation)
- [x] Backwards compatible (existing single-document workflow unchanged)

### Performance Requirements
- [ ] Handle batches of 50+ documents
- [ ] SSE updates with <1 second latency
- [ ] Progress bars update smoothly (no jank)
- [ ] Memory usage remains stable during large batches

---

## Appendix: Key Code Snippets

### Backend: Progress Callback in StagedPipelineProcessor

```python
class StagedPipelineProcessor:
    def __init__(
        self,
        model_manager: 'ModelManager',
        pdf_handler: 'PDFHandler',
        verbose: bool = False,
        enable_memory_profiling: bool = False,
        enable_system_monitoring: bool = True,
        prefer_quality: bool = True,
        progress_callback: Optional[Callable[[float, int, str], None]] = None
    ):
        # ... existing init
        self.progress_callback = progress_callback

    def _emit_progress(self, progress_pct: float, pages_completed: int, stage: str) -> None:
        """Emit progress if callback is set."""
        if self.progress_callback:
            try:
                self.progress_callback(progress_pct, pages_completed, stage)
            except Exception as e:
                logger.error(f"Progress callback error: {e}")

    def process_pdf(self, ...):
        # ... extraction

        # OCR stage
        for i, (page_num, page_text, page_img, is_scanned) in enumerate(pages_data):
            # ... OCR processing

            # Emit progress
            ocr_progress = (i + 1) / total_pages * 60.0  # OCR is 60% of total
            self._emit_progress(ocr_progress, i + 1, "ocr")

        # Merge stage
        self._emit_progress(70.0, total_pages, "merge")
        # ... merge processing

        # Format stage
        self._emit_progress(90.0, total_pages, "format")
        # ... format processing

        # Complete
        self._emit_progress(100.0, total_pages, "complete")
```

### Frontend: SSE Subscription in MessageList

```typescript
export function MessageList({ messages }: MessageListProps) {
  const [progressMap, setProgressMap] = useState<Map<string, InlineProgressData>>(new Map());

  useEffect(() => {
    const eventSource = new EventSource('/api/monitoring/stream');

    // Job progress (single/multi-page)
    eventSource.addEventListener('job_progress', (e) => {
      const data = JSON.parse(e.data);

      // Find message associated with this job
      const message = messages.find(m => m.metadata?.jobId === data.job_id);
      if (!message) return;

      // Update progress map
      setProgressMap(prev => {
        const newMap = new Map(prev);
        newMap.set(message.id, {
          type: data.total_pages > 1 ? 'multi-page' : 'single',
          progress_pct: data.progress_pct,
          content: `${data.stage} stage: ${data.current_page}/${data.total_pages} pages`,
          currentPage: data.current_page,
          totalPages: data.total_pages,
          stage: data.stage,
        });
        return newMap;
      });
    });

    // Batch progress
    eventSource.addEventListener('batch_progress', (e) => {
      const data = JSON.parse(e.data);

      // Find message associated with this batch
      const message = messages.find(m => m.metadata?.batchJobId === data.batch_job_id);
      if (!message) return;

      // Update progress map
      setProgressMap(prev => {
        const newMap = new Map(prev);
        newMap.set(message.id, {
          type: 'batch',
          progress_pct: data.overall_progress_pct,
          content: `Processing batch: ${data.documents_completed}/${data.total_documents} documents`,
          documentsCompleted: data.documents_completed,
          totalDocuments: data.total_documents,
          currentDocument: data.current_document?.filename,
          currentPage: data.current_document?.current_page,
          totalPages: data.current_document?.total_pages,
          stage: data.current_document?.stage,
        });
        return newMap;
      });
    });

    // Error handling
    eventSource.addEventListener('error', (e) => {
      console.error('SSE error:', e);
      // Optionally show error in UI
    });

    return () => eventSource.close();
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      {messages.map((msg) => (
        <ChatMessage
          key={msg.id}
          message={msg}
          inlineProgress={progressMap.get(msg.id)}
        />
      ))}
    </div>
  );
}
```

---

## Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-11-09 | Initial specification |

---

## Approval

**Specification Status:** Pending Approval

**Approved By:** _________________________

**Date:** _________________________

---

**End of Specification**
