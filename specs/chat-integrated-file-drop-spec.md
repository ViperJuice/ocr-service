# Chat-Integrated File Drop & Batch Processing Specification

**Version:** 1.0
**Date:** 2025-11-09
**Status:** Planning / Pre-Implementation
**Depends On:** `inline-progress-batch-processing-spec.md` (Backend complete)

---

## Executive Summary

This specification outlines the implementation of chat-integrated file drop functionality with batch processing support. Instead of separate upload zones, users drop files directly into the chat interface for a streamlined UX.

### Key Design Principles
1. **Single Interface**: All file operations happen in the chat
2. **Smart Detection**: Automatically detect single vs. batch uploads
3. **Inline Progress**: Show progress within chat messages
4. **Future-Ready**: Support for ZIP extraction and local paths

### Scope
- **3 files to modify** (ChatInput, page.tsx, command-parser)
- **3 new files to create** (useBatchJob hook, batch-utils, styles)
- **1 file to delete** (DirectoryUploadZone - no longer needed)
- **1 new dependency required** (jszip for ZIP extraction)

---

## Table of Contents

1. [Dependencies](#dependencies)
2. [Architecture Overview](#architecture-overview)
3. [Data Structures](#data-structures)
4. [Files to Create](#files-to-create)
5. [Files to Modify](#files-to-modify)
6. [Files to Delete](#files-to-delete)
7. [Implementation Details](#implementation-details)
8. [User Flow](#user-flow)
9. [Future Enhancements](#future-enhancements)

---

## Dependencies

### Frontend Dependencies (1 New Required)

**New Dependency Required:**

```bash
npm install jszip @types/jszip
```

**Purpose:** ZIP file extraction for batch processing

**Existing Dependencies (Already in package.json):**

```json
{
  "dependencies": {
    "next": "^16.0.1",              // React framework
    "react": "^19.2.0",              // UI library
    "react-dom": "^19.2.0",          // React DOM renderer
    "typescript": "^5.9.3",          // Type safety
    "lucide-react": "^0.553.0",      // Icons
    "tailwindcss": "^3.4.18",        // Styling
    "react-dropzone": "^14.3.8"      // OPTIONAL: Can use for advanced drop zones
  }
}
```

**Note:** We'll implement drag-and-drop using native browser APIs, so `react-dropzone` is optional.

### Backend Dependencies (Already Complete)

Backend batch processing is fully implemented. Available endpoints:
- `POST /api/v1/files/directories/upload`
- `POST /api/v1/batch/process`
- `GET /api/v1/batch/{batch_job_id}/status`
- `GET /api/v1/batch/{batch_job_id}/result`
- `POST /api/v1/batch/{batch_job_id}/cancel`
- `GET /api/v1/batch/progress/stream` (SSE)

---

## Architecture Overview

### Component Hierarchy

```
page.tsx (Main App)
├── MessageList
│   └── ChatMessage
│       └── InlineProgress (already created)
└── ChatInput (MODIFIED - add file drop)
    ├── Drag overlay
    ├── File preview
    └── Text input
```

### Data Flow

```
User drops files → ChatInput detects files → Determine upload type
                                              ↓
                    ┌─────────────────────────┼─────────────────────────┐
                    ↓                         ↓                         ↓
              Single file                Multiple files             ZIP file
                    ↓                         ↓                         ↓
           uploadFile() (existing)    uploadDirectory()        extractZip() (future)
                    ↓                         ↓                         ↓
           Show in chat               Show in chat              Show in chat
                    ↓                         ↓
    User types command          User types "parse directory"
                    ↓                         ↓
            submitJob()              submitBatchJob()
                    ↓                         ↓
        SSE progress updates         SSE batch progress
                    ↓                         ↓
          Show inline             Show inline batch progress
```

---

## Data Structures

### TypeScript Interfaces (Already Created)

Located in `/web/lib/types.ts`:

```typescript
// Batch types
export interface BatchJobStatus { ... }
export interface DocumentProgress { ... }
export interface BatchProgress { ... }
export interface DirectoryInfo { ... }
export interface InlineProgressData { ... }
export interface BatchResultResponse { ... }

// Updated types
export interface ChatMessage {
  inlineProgress?: InlineProgressData;  // NEW
  metadata?: {
    batchJobId?: string;  // NEW
    jobId?: string;
    ...
  };
}

export interface ParsedCommand {
  type: ... | "parse_directory";  // NEW
}
```

### New Helper Functions (To Be Created)

Located in `/web/lib/batch-utils.ts`:

```typescript
// Upload type detection
export function detectUploadType(files: FileList): 'single' | 'batch' | 'zip';

// File validation
export function validatePdfBatch(files: FileList): string[];

// ZIP handling (future)
export async function extractZipFile(zipFile: File): Promise<File[]>;

// Progress calculations
export function calculateBatchProgress(batch: BatchJobStatus): number;

// Result grouping
export function groupResultsByDocument(results: any[]): Map<string, any>;

// Status formatting
export function formatBatchStatus(status: string): string;

// Helper to create FileList from File[]
export function createFileList(files: File[]): FileList;
```

---

## Files to Create

### 1. `/web/hooks/useBatchJob.ts`

**Purpose:** Manage batch job lifecycle
**Exports:** `useBatchJob` hook

**Interface:**
```typescript
interface UseBatchJobReturn {
  currentDirectory: DirectoryInfo | null;
  currentBatchJob: BatchJobStatus | null;
  batchResult: BatchResultResponse | null;
  isUploading: boolean;
  uploadDirectory: (files: FileList, name: string) => Promise<DirectoryInfo>;
  submitBatchJob: (options: BatchJobOptions) => Promise<BatchJobStatus>;
  fetchBatchResult: (batchJobId: string) => Promise<BatchResultResponse>;
  reset: () => void;
}
```

**State Management:**
- `currentDirectory`: Uploaded directory metadata
- `currentBatchJob`: Active batch job status
- `batchResult`: Completed batch results
- `isUploading`: Upload in progress flag

**Methods:**
- `uploadDirectory()`: Upload multiple PDF files as directory
- `submitBatchJob()`: Submit batch processing job
- `fetchBatchResult()`: Fetch completed batch results
- `reset()`: Clear batch state

**Dependencies:**
- `apiClient` from `/web/lib/api-client.ts`
- React hooks: `useState`, `useCallback`

---

### 2. `/web/lib/batch-utils.ts`

**Purpose:** Utility functions for batch operations
**Exports:** 6 utility functions

**Functions:**

1. **`detectUploadType(files: FileList): 'single' | 'batch' | 'zip'`**
   - Detects upload type from FileList
   - Returns: 'single' (1 PDF), 'batch' (multiple PDFs), 'zip' (ZIP file)

2. **`validatePdfBatch(files: FileList): string[]`**
   - Validates all files are PDFs
   - Checks file sizes (< 100MB per file)
   - Returns: Array of error messages (empty if valid)

3. **`extractZipFile(zipFile: File): Promise<File[]>`**
   - **REQUIRED NOW**: Extract PDF files from ZIP archives
   - Uses jszip library to parse ZIP contents
   - Filters for .pdf files only
   - Returns array of extracted File objects

4. **`calculateBatchProgress(batch: BatchJobStatus): number`**
   - Calculates overall batch progress percentage
   - Formula: `(documents_completed / total_documents) * 100`

5. **`groupResultsByDocument(results: any[]): Map<string, any>`**
   - Groups batch results by document/job_id
   - Returns: Map of job_id → result

6. **`formatBatchStatus(status: string): string`**
   - Formats status for display
   - Maps: 'queued' → 'Queued', 'processing' → 'Processing', etc.

7. **`createFileList(files: File[]): FileList`**
   - Helper to convert File[] to FileList
   - Workaround for FileList constructor limitations

**Dependencies:**
- `BatchJobStatus` from `/web/lib/types.ts`
- `jszip` library (REQUIRED for ZIP extraction)

---

### 3. Add to `/web/styles/globals.css`

**Purpose:** Styles for file drop, progress, and batch UI

**New CSS Classes:**

```css
/* === FILE DROP STYLES === */

.chat-input-container {
  position: relative;
}

.drag-overlay {
  position: absolute;
  inset: 0;
  background-color: rgba(59, 130, 246, 0.1);
  border: 2px dashed rgb(59, 130, 246);
  border-radius: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
  pointer-events: none;
  animation: pulse 2s ease-in-out infinite;
}

.drag-overlay-text {
  font-size: 1.125rem;
  font-weight: 600;
  color: rgb(59, 130, 246);
}

/* File preview in chat input */
.file-preview {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  background-color: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 0.375rem;
  margin-bottom: 0.5rem;
  transition: all 0.2s ease;
}

.file-preview-single {
  border-left: 3px solid rgb(59, 130, 246);
}

.file-preview-batch {
  border-left: 3px solid rgb(147, 51, 234);
}

.file-preview-item {
  font-size: 0.875rem;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

/* === INLINE PROGRESS STYLES === */

.inline-progress-container {
  margin-top: 0.75rem;
  padding: 0.75rem;
  background-color: rgba(59, 130, 246, 0.1);
  border-left: 3px solid rgb(59, 130, 246);
  border-radius: 0.375rem;
  animation: slide-in 0.3s ease-out;
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

/* === BATCH PROGRESS STYLES === */

.batch-progress-card {
  margin-top: 1rem;
  padding: 1rem;
  background-color: rgba(147, 51, 234, 0.1);
  border: 1px solid rgba(147, 51, 234, 0.3);
  border-radius: 0.5rem;
  animation: slide-in 0.3s ease-out;
}

.document-progress-item {
  padding: 0.5rem;
  margin-top: 0.5rem;
  background-color: rgba(255, 255, 255, 0.05);
  border-radius: 0.375rem;
  border: 1px solid transparent;
  transition: all 0.2s ease;
}

.document-progress-item:hover {
  background-color: rgba(255, 255, 255, 0.08);
  border-color: rgba(59, 130, 246, 0.3);
}

/* === STAGE COLORS === */

.stage-ocr {
  color: rgb(59, 130, 246);
}

.stage-merge {
  color: rgb(147, 51, 234);
}

.stage-format {
  color: rgb(34, 197, 94);
}

/* === ANIMATIONS === */

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.7;
  }
}

@keyframes slide-in {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
```

---

## Files to Modify

### 1. `/web/components/ChatInput.tsx`

**Current:** Text input with suggestions
**New:** Text input + file drop zone + file preview

**Props (Modified):**
```typescript
interface ChatInputProps {
  onSend: (message: string) => void;
  onFilesDropped?: (files: File[]) => void;  // NEW
  disabled?: boolean;
  isProcessing?: boolean;
  placeholder?: string;
  droppedFiles?: File[];  // NEW - for external state management
  onClearFiles?: () => void;  // NEW
}
```

**New State:**
```typescript
const [isDragging, setIsDragging] = useState(false);
const [localDroppedFiles, setLocalDroppedFiles] = useState<File[]>([]);
```

**New Methods:**
```typescript
const handleDrop = (e: React.DragEvent) => {
  e.preventDefault();
  setIsDragging(false);
  const files = Array.from(e.dataTransfer.files);

  // Filter only PDF files
  const pdfFiles = files.filter(f => f.type === 'application/pdf');

  if (pdfFiles.length > 0) {
    if (onFilesDropped) {
      onFilesDropped(pdfFiles);
    } else {
      setLocalDroppedFiles(pdfFiles);
    }
  }
};

const handleDragOver = (e: React.DragEvent) => {
  e.preventDefault();
  setIsDragging(true);
};

const handleDragLeave = (e: React.DragEvent) => {
  e.preventDefault();
  setIsDragging(false);
};

const clearFiles = () => {
  setLocalDroppedFiles([]);
  if (onClearFiles) {
    onClearFiles();
  }
};
```

**New JSX Elements:**
```tsx
<div
  className="chat-input-container"
  onDrop={handleDrop}
  onDragOver={handleDragOver}
  onDragLeave={handleDragLeave}
>
  {/* Drag overlay */}
  {isDragging && (
    <div className="drag-overlay">
      <span className="drag-overlay-text">
        Drop PDF files here
      </span>
    </div>
  )}

  {/* File preview */}
  {files.length > 0 && (
    <div className={`file-preview ${files.length > 1 ? 'file-preview-batch' : 'file-preview-single'}`}>
      <FileText className="w-4 h-4" />
      <span className="file-preview-item">
        {files.length === 1
          ? files[0].name
          : `${files.length} files ready`
        }
      </span>
      <button onClick={clearFiles} className="ml-auto">
        <X className="w-4 h-4" />
      </button>
    </div>
  )}

  {/* Existing textarea */}
  <textarea ... />

  {/* Existing send button */}
  <button ... />
</div>
```

**Dependencies:**
- Add icons: `FileText`, `X` from `lucide-react`

---

### 2. `/web/app/page.tsx`

**Current:** Single file upload workflow
**New:** Single + batch file upload workflow

**New Imports:**
```typescript
import { useBatchJob } from "@/hooks/useBatchJob";
import { detectUploadType, validatePdfBatch, createFileList, extractZipFile } from "@/lib/batch-utils";
```

**New State:**
```typescript
const [droppedFiles, setDroppedFiles] = useState<File[]>([]);
const [uploadType, setUploadType] = useState<'single' | 'batch' | null>(null);
```

**New Hook:**
```typescript
const {
  currentDirectory,
  currentBatchJob,
  batchResult,
  uploadDirectory,
  submitBatchJob,
  fetchBatchResult,
  reset: resetBatch,
  isUploading: isUploadingBatch,
} = useBatchJob();
```

**New Handler:**
```typescript
const handleFilesDropped = useCallback(async (files: File[]) => {
  const type = detectUploadType(createFileList(files));
  setUploadType(type);
  setDroppedFiles(files);

  if (type === 'single') {
    addMessage("system", `Uploading ${files[0].name}...`);
    try {
      await uploadFile(files[0]);
      addMessage("system", `File uploaded! What would you like to do?`);
      setDroppedFiles([]);
    } catch (error: any) {
      addMessage("system", `Upload failed: ${error.message}`);
    }
  } else if (type === 'batch') {
    // Validate files
    const errors = validatePdfBatch(createFileList(files));
    if (errors.length > 0) {
      addMessage("system", `Validation errors: ${errors.join(', ')}`);
      return;
    }

    addMessage("system", `Uploading ${files.length} files...`);
    try {
      const fileList = createFileList(files);
      const directory = await uploadDirectory(fileList, `batch_${Date.now()}`);
      addMessage("system", `Uploaded ${directory.file_count} files. Type "parse the whole directory" to process.`);
      setDroppedFiles([]);
    } catch (error: any) {
      addMessage("system", `Upload failed: ${error.message}`);
    }
  } else if (type === 'zip') {
    addMessage("system", `ZIP file detected. Extracting PDFs...`);
    try {
      const extractedFiles = await extractZipFile(files[0]);
      if (extractedFiles.length === 0) {
        addMessage("system", `No PDF files found in ZIP archive.`);
        return;
      }

      addMessage("system", `Extracted ${extractedFiles.length} PDF file(s). Uploading...`);
      const fileList = createFileList(extractedFiles);
      const directory = await uploadDirectory(fileList, `zip_${Date.now()}`);
      addMessage("system", `Uploaded ${directory.file_count} files. Type "parse the whole directory" to process.`);
      setDroppedFiles([]);
    } catch (error: any) {
      addMessage("system", `ZIP extraction failed: ${error.message}`);
    }
  }
}, [uploadFile, uploadDirectory, addMessage]);
```

**Modified Handler:**
```typescript
const handleCommand = useCallback(async (userInput: string) => {
  addMessage("user", userInput);

  const command = parseCommand(userInput);

  // NEW: Handle batch directory command
  if (command.type === "parse_directory") {
    if (!currentDirectory) {
      addMessage("system", "Please upload a directory of files first.");
      return;
    }

    const systemMsg: ChatMessage = {
      id: generateId(),
      role: "system",
      content: "Starting batch processing...",
      timestamp: Date.now(),
      metadata: { batchJobId: null },
    };
    setMessages((prev) => [...prev, systemMsg]);

    try {
      const batch = await submitBatchJob({
        output_format: outputFormat,
        processing_options: { prefer_quality: true },
      });

      // Update message with batch ID for SSE tracking
      setMessages((prev) =>
        prev.map((m) =>
          m.id === systemMsg.id
            ? { ...m, metadata: { ...m.metadata, batchJobId: batch.batch_job_id } }
            : m
        )
      );
    } catch (error: any) {
      addMessage("system", `Batch job failed: ${error.message}`);
    }
    return;
  }

  // Existing single-document command handling...
}, [currentDirectory, submitBatchJob, outputFormat, addMessage]);
```

**Modified JSX:**
```tsx
<ChatInput
  onSend={handleCommand}
  onFilesDropped={handleFilesDropped}  // NEW
  onClearFiles={() => setDroppedFiles([])}  // NEW
  droppedFiles={droppedFiles}  // NEW
  disabled={isUploadingSingle || isUploadingBatch}
  isProcessing={currentJob?.status === 'processing' || currentBatchJob?.status === 'processing'}
  placeholder={
    currentDirectory
      ? `${currentDirectory.file_count} files ready. Type "parse the whole directory" to begin.`
      : currentFile
      ? `File ready: ${currentFile.filename}. What would you like to do?`
      : "Type a message or drop PDF files here..."
  }
/>
```

---

### 3. `/web/lib/command-parser.ts`

**Current:** Parses single-document commands
**New:** Add batch directory command parsing

**Modified Function:**
```typescript
export function parseCommand(input: string): ParsedCommand {
  const normalized = input.toLowerCase().trim();

  // NEW: Parse directory/batch commands
  if (
    normalized.match(/parse (the )?(whole |entire )?(directory|batch|all files)/)
  ) {
    return {
      type: "parse_directory",
      params: {},
      originalText: input,
    };
  }

  // Existing command parsing...

  if (normalized.match(/parse (the )?(whole |entire )?document/)) {
    return { type: "parse_all", params: {}, originalText: input };
  }

  // ... rest of existing logic
}
```

**Modified Suggestions:**
```typescript
export function getSuggestions(input: string): string[] {
  const allSuggestions = [
    "Parse the whole document",
    "Parse page 5",
    "Parse pages 1-10",
    "Parse front matter on page 1",
    "Parse the whole directory",  // NEW
    "Parse all files",             // NEW
    "Show as JSON",
    "Show as text",
  ];

  // Existing filter logic...
}
```

---

## Files to Delete

### 1. `/web/components/DirectoryUploadZone.tsx`

**Why:** No longer needed - file drops integrated into ChatInput

This component was created earlier but is now superseded by the chat-integrated approach.

---

## Implementation Details

### Phase 5: Hooks & Utilities (1-2 days)

**Task 1: Create `useBatchJob` hook**

Location: `/web/hooks/useBatchJob.ts`

```typescript
import { useState, useCallback } from "react";
import { apiClient } from "@/lib/api-client";
import { DirectoryInfo, BatchJobStatus, BatchResultResponse } from "@/lib/types";

export function useBatchJob() {
  const [currentDirectory, setCurrentDirectory] = useState<DirectoryInfo | null>(null);
  const [currentBatchJob, setCurrentBatchJob] = useState<BatchJobStatus | null>(null);
  const [batchResult, setBatchResult] = useState<BatchResultResponse | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  const uploadDirectory = useCallback(async (files: FileList, name: string) => {
    setIsUploading(true);
    try {
      const directory = await apiClient.uploadDirectory(files, name);
      setCurrentDirectory(directory);
      return directory;
    } finally {
      setIsUploading(false);
    }
  }, []);

  const submitBatchJob = useCallback(async (options: {
    output_format?: string;
    processing_options?: any;
    model?: string;
  }) => {
    if (!currentDirectory) {
      throw new Error("No directory uploaded");
    }

    const batch = await apiClient.submitBatchJob({
      directory_id: currentDirectory.directory_id,
      ...options,
    });
    setCurrentBatchJob(batch);
    return batch;
  }, [currentDirectory]);

  const fetchBatchResult = useCallback(async (batchJobId: string) => {
    const result = await apiClient.getBatchResult(batchJobId);
    setBatchResult(result);
    return result;
  }, []);

  const reset = useCallback(() => {
    setCurrentDirectory(null);
    setCurrentBatchJob(null);
    setBatchResult(null);
  }, []);

  return {
    currentDirectory,
    currentBatchJob,
    batchResult,
    isUploading,
    uploadDirectory,
    submitBatchJob,
    fetchBatchResult,
    reset,
  };
}
```

**Task 2: Create `batch-utils.ts`**

Location: `/web/lib/batch-utils.ts`

```typescript
import { BatchJobStatus } from "./types";

export function detectUploadType(files: FileList): 'single' | 'batch' | 'zip' {
  if (files.length === 0) return 'single';
  if (files.length === 1) {
    const file = files[0];
    if (file.name.endsWith('.zip')) return 'zip';
    return 'single';
  }
  return 'batch';
}

export function validatePdfBatch(files: FileList): string[] {
  const errors: string[] = [];
  const fileArray = Array.from(files);

  // Check all files are PDFs
  const nonPdfFiles = fileArray.filter((f) => f.type !== "application/pdf");
  if (nonPdfFiles.length > 0) {
    errors.push(`${nonPdfFiles.length} non-PDF file(s) detected`);
  }

  // Check file sizes
  const oversizedFiles = fileArray.filter((f) => f.size > 100 * 1024 * 1024);
  if (oversizedFiles.length > 0) {
    errors.push(`${oversizedFiles.length} file(s) exceed 100MB limit`);
  }

  return errors;
}

export async function extractZipFile(zipFile: File): Promise<File[]> {
  const JSZip = (await import('jszip')).default;
  const zip = new JSZip();
  const contents = await zip.loadAsync(zipFile);

  const pdfFiles: File[] = [];

  for (const [filename, file] of Object.entries(contents.files)) {
    if (filename.endsWith('.pdf') && !file.dir) {
      const blob = await file.async('blob');
      pdfFiles.push(new File([blob], filename, { type: 'application/pdf' }));
    }
  }

  return pdfFiles;
}

export function calculateBatchProgress(batch: BatchJobStatus): number {
  return (batch.documents_completed / batch.total_documents) * 100;
}

export function groupResultsByDocument(results: any[]): Map<string, any> {
  return new Map(results.map((r) => [r.job_id, r]));
}

export function formatBatchStatus(status: string): string {
  const statusMap: Record<string, string> = {
    queued: "Queued",
    processing: "Processing",
    completed: "Completed",
    failed: "Failed",
    cancelled: "Cancelled",
  };
  return statusMap[status] || status;
}

export function createFileList(files: File[]): FileList {
  const dataTransfer = new DataTransfer();
  files.forEach(file => dataTransfer.items.add(file));
  return dataTransfer.files;
}
```

**Task 3: Modify command parser**

- Add batch command patterns
- Add batch suggestions

---

### Phase 6: Main Application Integration (2 days)

**Task 1: Modify ChatInput**

- Add drag-and-drop handlers
- Add file preview UI
- Add clear files button
- Update placeholder based on state

**Task 2: Modify page.tsx**

- Import and use `useBatchJob` hook
- Add `handleFilesDropped` handler
- Modify `handleCommand` for batch support
- Pass props to ChatInput

**Task 3: Update ResultViewer (optional)**

- Add batch result display
- Show all document results in batch

---

### Phase 7: Styling (1 day)

**Task 1: Add CSS to globals.css**

- File drop overlay styles
- File preview styles
- Progress styles (inline, batch, document)
- Stage color classes
- Animations

---

## User Flow

### Single File Flow

1. User drags PDF into chat
2. ChatInput shows file preview: "document.pdf"
3. File uploads automatically
4. System message: "File uploaded! What would you like to do?"
5. User types: "Parse the whole document"
6. Inline progress appears in chat
7. Results display when complete

### Batch Directory Flow

1. User drags 10 PDFs into chat
2. ChatInput shows: "10 files ready"
3. Files upload as directory
4. System message: "Uploaded 10 files. Type 'parse the whole directory' to process."
5. User types: "Parse the whole directory"
6. Inline batch progress appears
7. Shows: "Documents: 3/10" with current document progress
8. Batch results display when complete

### ZIP File Flow

1. User drags ZIP file into chat
2. ChatInput shows: "archive.zip"
3. System message: "ZIP file detected. Extracting PDFs..."
4. ZIP extracts to PDF files using jszip
5. System message: "Extracted 15 PDF file(s). Uploading..."
6. Files upload as directory
7. System message: "Uploaded 15 files. Type 'parse the whole directory' to process."
8. User types: "Parse the whole directory"
9. Continues as batch directory flow

---

## Future Enhancements

### 1. Local File Storage and Unextracted Batch Parsing

**Purpose:** Support storing uploaded files locally without extraction, and enable batch parsing of stored files.

**Architecture Considerations:**
- Current implementation extracts ZIPs and uploads files immediately
- Future: Add option to store ZIP files unextracted in local storage
- Add API endpoints for listing locally stored files/directories
- Add command patterns for parsing stored files by path reference

**Implementation Notes:**
- Keep existing extraction flow as default
- Add `storage_mode` parameter to API: `'extract'` (default) or `'store_unextracted'`
- Maintain backward compatibility with current batch processing

### 2. Path-based File References

When local file storage is implemented, allow users to reference stored files by path:

```typescript
interface ChatInputProps {
  onPathSubmit?: (path: string) => void;  // NEW
}

// User types: /stored/documents/batch-2024
// System detects path pattern and calls onPathSubmit
// Processes files from local storage without re-upload
```

### 3. Progress Persistence

Store progress in localStorage to survive refreshes:

```typescript
useEffect(() => {
  if (currentBatchJob) {
    localStorage.setItem('activeBatchJob', currentBatchJob.batch_job_id);
  }
}, [currentBatchJob]);
```

### 4. Batch Result Download

Add "Download All" button for batch results:

```typescript
const downloadAllResults = async () => {
  const zip = new JSZip();
  batchResult.results.forEach((result, index) => {
    zip.file(`document_${index + 1}.md`, result.content);
  });
  const blob = await zip.generateAsync({ type: 'blob' });
  // Trigger download
};
```

---

## Testing Checklist

### Unit Tests

- [ ] `detectUploadType()` correctly identifies upload types
- [ ] `validatePdfBatch()` catches invalid files
- [ ] `calculateBatchProgress()` computes correctly
- [ ] `useBatchJob` hook state management works

### Integration Tests

- [ ] Single file drop uploads correctly
- [ ] Multiple files create batch
- [ ] Batch command triggers batch job
- [ ] SSE progress updates appear inline
- [ ] File preview shows correct count
- [ ] Clear files button works

### E2E Tests

- [ ] Complete single-file workflow
- [ ] Complete batch workflow
- [ ] Cancel batch mid-processing
- [ ] Error handling for invalid files
- [ ] Network error recovery

---

## Success Criteria

### Functional

- [x] Files can be dropped into chat
- [x] Single file triggers standard upload
- [x] Multiple files trigger batch upload
- [x] Inline progress displays in chat
- [x] Batch progress shows hierarchical info
- [x] Commands work for both modes

### Non-Functional

- [x] No new dependencies required
- [x] Clean, intuitive UX
- [x] Responsive drag-and-drop
- [x] Smooth progress animations
- [x] Accessible (keyboard, screen readers)

---

## Appendix

### File Summary

**Created (3):**
1. `/web/hooks/useBatchJob.ts` - Batch job state management
2. `/web/lib/batch-utils.ts` - Utility functions
3. CSS additions to `/web/styles/globals.css`

**Modified (3):**
1. `/web/components/ChatInput.tsx` - Add file drop + preview
2. `/web/app/page.tsx` - Integrate batch workflow
3. `/web/lib/command-parser.ts` - Add batch commands

**Deleted (1):**
1. `/web/components/DirectoryUploadZone.tsx` - Superseded by chat integration

**Already Complete (4):**
1. `/web/components/InlineProgress.tsx`
2. `/web/components/BatchProgressCard.tsx`
3. `/web/components/DocumentProgressItem.tsx`
4. `/web/components/MessageList.tsx` (SSE subscriptions)

---

**End of Specification**
