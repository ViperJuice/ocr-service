  # OCR Service API Implementation

## Overview

The OCR Service API has been successfully implemented according to the specification in [specs/api-implementation.md](../specs/api-implementation.md). This document provides quick start instructions and implementation notes.

## Quick Start

### 1. Start the API Server

**Development Mode (with auto-reload):**
```bash
OCR_API_RELOAD=true ./scripts/start_api.sh
```

**Production Mode:**
```bash
./scripts/start_api.sh
```

**Custom Configuration:**
```bash
OCR_API_HOST=0.0.0.0 OCR_API_PORT=8080 OCR_API_WORKERS=4 ./scripts/start_api.sh
```

### 2. Access API Documentation

Once the server is running, visit:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **OpenAPI Schema:** http://localhost:8000/openapi.json

### 3. Basic Usage Example

```bash
# 1. Upload a PDF file
curl -X POST http://localhost:8000/api/v1/process/upload \
  -F "file=@document.pdf" \
  > upload_response.json

# Extract file_id from response
FILE_ID=$(cat upload_response.json | jq -r '.file_id')

# 2. Submit processing job
curl -X POST http://localhost:8000/api/v1/process/jobs \
  -H "Content-Type: application/json" \
  -d "{
    \"file_id\": \"$FILE_ID\",
    \"model\": \"qwen2-vl-7b\",
    \"output_format\": \"markdown\"
  }" \
  > job_response.json

# Extract job_id
JOB_ID=$(cat job_response.json | jq -r '.job_id')

# 3. Monitor progress (SSE stream)
curl -N http://localhost:8000/api/monitoring/stream?job_id=$JOB_ID

# 4. Check job status
curl http://localhost:8000/api/v1/process/jobs/$JOB_ID

# 5. Get results (once completed)
curl http://localhost:8000/api/v1/process/jobs/$JOB_ID/result

# 6. Download results as file
curl http://localhost:8000/api/v1/process/jobs/$JOB_ID/result/download \
  -o result.md
```

## Implementation Summary

### ✅ Core Components Implemented

1. **Data Models** ([src/api/models/](../src/api/models/))
   - Request models: `JobSubmitRequest`, `ProcessingOptions`, `PromptValidationRequest`
   - Response models: `FileUploadResponse`, `JobStatusResponse`, `JobResultResponse`, etc.
   - Full validation with Pydantic v2

2. **Service Layer** ([src/api/services/](../src/api/services/))
   - **FileManager**: File upload/storage with automatic expiration
   - **PromptManager**: Custom prompt validation and merging
   - **JobManager**: Job lifecycle management with async processing

3. **API Routes** ([src/api/](../src/api/))
   - **Processing Routes**: File upload, job submission, status, results
   - **Configuration Routes**: Models list, prompts list, settings
   - **File Routes**: File metadata, deletion
   - **Monitoring Routes**: Real-time SSE streams (already existed)

4. **Middleware** ([src/api/middleware/](../src/api/middleware/))
   - Global error handling
   - CORS configuration
   - Request validation

5. **Core Integration**
   - ✅ Updated `BaseVLModel` to accept `prompts` parameter
   - ✅ Updated `QwenVLModel` methods: `process_image`, `merge_texts`, `format_with_visual`
   - ✅ Updated `DeepSeekOCR` methods: `process_image`, `merge_texts`, `format_with_visual`
   - ✅ Updated `StagedPipelineProcessor` to support `job_id` and `prompts`
   - ✅ Updated `SystemMonitor` to include `job_id` in logged events
   - ✅ Added API storage configuration to `settings.py`

### 🎯 Key Features

- **Async Processing**: Jobs run in background threads
- **Custom Prompts**: Per-job prompt overrides without system restart
- **Progress Tracking**: Real-time SSE streams with job correlation
- **File Management**: Automatic cleanup of expired uploads
- **Error Handling**: Comprehensive error responses with proper HTTP codes
- **OpenAPI Documentation**: Auto-generated interactive docs

### 📁 Directory Structure

```
src/api/
├── main.py                    # FastAPI application
├── processing_routes.py       # Processing endpoints
├── config_routes.py           # Configuration endpoints
├── file_routes.py             # File management endpoints
├── monitoring_routes.py       # (Already existed)
├── models/
│   ├── requests.py           # Request schemas
│   ├── responses.py          # Response schemas
│   └── __init__.py
├── services/
│   ├── file_manager.py       # File upload/storage
│   ├── prompt_manager.py     # Prompt validation
│   ├── job_manager.py        # Job lifecycle
│   └── __init__.py
└── middleware/
    ├── error_handler.py      # Error handling
    └── __init__.py

data/
├── temp/                     # Uploaded files (6h expiry)
├── processing/               # Active job workspace
└── output/                   # Completed results
```

### 🔧 Configuration

Environment variables (set in `.env` or export):

```bash
# API Server
OCR_API_HOST=0.0.0.0
OCR_API_PORT=8000
OCR_API_WORKERS=1

# CORS
OCR_ENABLE_CORS=true
OCR_CORS_ORIGINS=["http://localhost:3000"]

# Upload Limits
OCR_MAX_UPLOAD_SIZE_MB=50
OCR_TEMP_FILE_EXPIRY_HOURS=6

# Processing
OCR_DEFAULT_MODEL=deepseek-ocr
OCR_MAX_BATCH_SIZE=10
```

### 🔄 Job Lifecycle

```
1. Upload File → FileManager → data/temp/{file_id}/
2. Submit Job → JobManager → Create job with QUEUED status
3. Start Processing → Background thread → PROCESSING status
4. Update Progress → SystemMonitor → SSE stream
5. Complete → Save results → COMPLETED status
6. Retrieve Results → Return content or download file
```

### 📝 Example: Custom Prompts

```bash
curl -X POST http://localhost:8000/api/v1/process/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "file_id": "your-file-id",
    "custom_prompts": {
      "merge": "You are a medical document specialist. Merge these texts carefully preserving medical terminology: Embedded: {embedded_text}, OCR: {ocr_text}"
    },
    "output_format": "markdown"
  }'
```

### 🧪 Testing

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run API tests (when implemented)
pytest tests/api/
```

### 📊 Monitoring

Job progress can be monitored via SSE:

```bash
curl -N http://localhost:8000/api/monitoring/stream?job_id=<job-id>
```

Events include:
- Periodic metrics (GPU, CPU, memory)
- Stage transitions (ocr → merge)
- Page completions
- All events include `job_id` for correlation

### 🐛 Troubleshooting

**API won't start:**
- Check dependencies: `pip install -e .`
- Verify no port conflicts: `lsof -i :8000`
- Check logs for errors

**Jobs fail immediately:**
- Ensure models are downloaded
- Check GPU availability
- Verify file permissions in `data/` directories

**File upload fails:**
- Check file size < `max_upload_size_mb`
- Verify file type (PDF, PNG, JPEG, TIFF, BMP only)
- Ensure `data/temp/` exists and is writable

### 🚀 Next Steps

The core API is complete per the specification. Future enhancements could include:

- [ ] Authentication/authorization (OAuth2, API keys)
- [ ] Rate limiting
- [ ] Webhook notifications on job completion
- [ ] Batch processing (multiple files in one job)
- [ ] Resume/retry functionality via API
- [ ] WebSocket alternative to SSE
- [ ] Result caching and CDN integration
- [ ] Database persistence (currently in-memory)
- [ ] Unit and integration tests

### 📚 References

- Full API Specification: [specs/api-implementation.md](../specs/api-implementation.md)
- FastAPI Documentation: https://fastapi.tiangolo.com/
- Pydantic Documentation: https://docs.pydantic.dev/
