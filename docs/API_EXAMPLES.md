# OCR Service API - Usage Examples

## Table of Contents

1. [Basic Workflow](#basic-workflow)
2. [Custom Prompts](#custom-prompts)
3. [Page Range Selection](#page-range-selection)
4. [Monitoring Progress](#monitoring-progress)
5. [Error Handling](#error-handling)
6. [Python Client Example](#python-client-example)

## Basic Workflow

### 1. Upload a PDF File

```bash
curl -X POST http://localhost:8000/api/v1/process/upload \
  -F "file=@/path/to/document.pdf" \
  | jq '.'
```

**Response:**
```json
{
  "file_id": "123e4567-e89b-12d3-a456-426614174000",
  "filename": "document.pdf",
  "size_bytes": 2048576,
  "mime_type": "application/pdf",
  "uploaded_at": "2025-01-08T12:00:00Z",
  "expires_at": "2025-01-08T18:00:00Z"
}
```

### 2. Submit Processing Job

```bash
curl -X POST http://localhost:8000/api/v1/process/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "file_id": "123e4567-e89b-12d3-a456-426614174000",
    "model": "qwen2-vl-7b",
    "output_format": "markdown"
  }' \
  | jq '.'
```

**Response:**
```json
{
  "job_id": "987fcdeb-51a2-43f1-9876-123456789abc",
  "status": "queued",
  "created_at": "2025-01-08T12:00:05Z",
  "file_id": "123e4567-e89b-12d3-a456-426614174000",
  "estimated_pages": 22,
  "monitor_url": "/api/monitoring/stream?job_id=987fcdeb-51a2-43f1-9876-123456789abc"
}
```

### 3. Check Job Status

```bash
curl http://localhost:8000/api/v1/process/jobs/987fcdeb-51a2-43f1-9876-123456789abc \
  | jq '.'
```

**Response (Processing):**
```json
{
  "job_id": "987fcdeb-51a2-43f1-9876-123456789abc",
  "status": "processing",
  "created_at": "2025-01-08T12:00:05Z",
  "started_at": "2025-01-08T12:00:10Z",
  "completed_at": null,
  "file_id": "123e4567-e89b-12d3-a456-426614174000",
  "filename": "document.pdf",
  "total_pages": 22,
  "pages_completed": 15,
  "current_stage": "merge",
  "progress_pct": 68.2,
  "estimated_remaining_seconds": 45,
  "error": null
}
```

### 4. Get Results

```bash
curl http://localhost:8000/api/v1/process/jobs/987fcdeb-51a2-43f1-9876-123456789abc/result \
  | jq '.'
```

**Response:**
```json
{
  "job_id": "987fcdeb-51a2-43f1-9876-123456789abc",
  "status": "completed",
  "result": {
    "format": "markdown",
    "content": "# Document Title\n\n## Section 1\n\nExtracted text...",
    "total_pages": 22,
    "processing_time_seconds": 245.3,
    "model_used": "qwen2-vl-7b",
    "metadata": {
      "dpi": 300,
      "method": "auto",
      "pages_processed": 22
    }
  },
  "completed_at": "2025-01-08T12:04:05Z"
}
```

### 5. Download Result as File

```bash
curl http://localhost:8000/api/v1/process/jobs/987fcdeb-51a2-43f1-9876-123456789abc/result/download \
  -o result.md
```

## Custom Prompts

### Using Custom Merge Prompt

```bash
curl -X POST http://localhost:8000/api/v1/process/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "file_id": "123e4567-e89b-12d3-a456-426614174000",
    "model": "qwen2-vl-7b",
    "custom_prompts": {
      "merge": "You are a medical document specialist. Merge these texts carefully preserving medical terminology:\nEmbedded: {embedded_text}\nOCR: {ocr_text}\nProvide the most accurate merged version."
    },
    "output_format": "markdown"
  }' \
  | jq '.'
```

### Validating Custom Prompts

```bash
curl -X POST http://localhost:8000/api/v1/config/prompts/validate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt_type": "merge",
    "template": "Merge: {embedded_text} and {ocr_text}",
    "model": "qwen2-vl-7b"
  }' \
  | jq '.'
```

**Response:**
```json
{
  "valid": true,
  "warnings": [],
  "required_variables": ["image", "embedded_text", "ocr_text"],
  "found_variables": ["embedded_text", "ocr_text"]
}
```

## Page Range Selection

### Process Only Pages 5-10

```bash
curl -X POST http://localhost:8000/api/v1/process/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "file_id": "123e4567-e89b-12d3-a456-426614174000",
    "model": "qwen2-vl-7b",
    "processing_options": {
      "start_page": 5,
      "end_page": 10,
      "dpi": 300
    },
    "output_format": "markdown"
  }' \
  | jq '.'
```

### High-Quality Processing

```bash
curl -X POST http://localhost:8000/api/v1/process/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "file_id": "123e4567-e89b-12d3-a456-426614174000",
    "model": "qwen2-vl-7b",
    "processing_options": {
      "dpi": 600,
      "prefer_quality": true,
      "method": "hybrid"
    },
    "output_format": "markdown"
  }' \
  | jq '.'
```

## Monitoring Progress

### SSE Stream (Real-Time Updates)

```bash
curl -N http://localhost:8000/api/monitoring/stream?job_id=987fcdeb-51a2-43f1-9876-123456789abc
```

**Sample Output:**
```
data: {"timestamp":"2025-01-08T12:00:15Z","job_id":"987fcdeb...","active_stage":"ocr","stage_page":3,"stage_total_pages":22,"overall_progress_pct":6.8}

data: {"timestamp":"2025-01-08T12:00:45Z","job_id":"987fcdeb...","active_stage":"ocr","stage_page":10,"stage_total_pages":22,"overall_progress_pct":22.7}

data: {"timestamp":"2025-01-08T12:02:00Z","job_id":"987fcdeb...","active_stage":"merge","stage_page":5,"stage_total_pages":22,"overall_progress_pct":61.4}
```

### Polling for Status Updates

```bash
# Poll every 5 seconds
while true; do
  STATUS=$(curl -s http://localhost:8000/api/v1/process/jobs/987fcdeb-51a2-43f1-9876-123456789abc | jq -r '.status')
  PROGRESS=$(curl -s http://localhost:8000/api/v1/process/jobs/987fcdeb-51a2-43f1-9876-123456789abc | jq -r '.progress_pct')
  echo "Status: $STATUS | Progress: $PROGRESS%"

  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
    break
  fi

  sleep 5
done
```

## Error Handling

### Invalid File Upload

```bash
curl -X POST http://localhost:8000/api/v1/process/upload \
  -F "file=@invalid.txt"
```

**Response (400 Bad Request):**
```json
{
  "error": "Invalid file type: text/plain. Allowed types: PDF, PNG, JPEG, TIFF, BMP",
  "code": "HTTP_400"
}
```

### Job Not Found

```bash
curl http://localhost:8000/api/v1/process/jobs/invalid-job-id
```

**Response (404 Not Found):**
```json
{
  "error": "Job not found: invalid-job-id",
  "code": "HTTP_404"
}
```

### Validation Error

```bash
curl -X POST http://localhost:8000/api/v1/process/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "file_id": "123e4567-e89b-12d3-a456-426614174000",
    "processing_options": {
      "start_page": 10,
      "end_page": 5
    }
  }'
```

**Response (422 Unprocessable Entity):**
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

## Python Client Example

### Simple Client

```python
import requests
import time
from pathlib import Path

class OCRClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url

    def upload_file(self, file_path):
        """Upload a file for processing."""
        with open(file_path, 'rb') as f:
            files = {'file': f}
            response = requests.post(
                f"{self.base_url}/api/v1/process/upload",
                files=files
            )
            response.raise_for_status()
            return response.json()

    def submit_job(self, file_id, model="qwen2-vl-7b", **options):
        """Submit a processing job."""
        data = {
            "file_id": file_id,
            "model": model,
            **options
        }
        response = requests.post(
            f"{self.base_url}/api/v1/process/jobs",
            json=data
        )
        response.raise_for_status()
        return response.json()

    def get_job_status(self, job_id):
        """Get job status."""
        response = requests.get(
            f"{self.base_url}/api/v1/process/jobs/{job_id}"
        )
        response.raise_for_status()
        return response.json()

    def wait_for_completion(self, job_id, poll_interval=5):
        """Wait for job to complete."""
        while True:
            status = self.get_job_status(job_id)

            if status['status'] in ['completed', 'failed', 'cancelled']:
                return status

            print(f"Progress: {status['progress_pct']:.1f}% "
                  f"({status['pages_completed']}/{status['total_pages']} pages)")
            time.sleep(poll_interval)

    def get_result(self, job_id):
        """Get job result."""
        response = requests.get(
            f"{self.base_url}/api/v1/process/jobs/{job_id}/result"
        )
        response.raise_for_status()
        return response.json()

    def download_result(self, job_id, output_path):
        """Download result to file."""
        response = requests.get(
            f"{self.base_url}/api/v1/process/jobs/{job_id}/result/download"
        )
        response.raise_for_status()

        with open(output_path, 'wb') as f:
            f.write(response.content)

# Example usage
if __name__ == "__main__":
    client = OCRClient()

    # Upload file
    print("Uploading file...")
    upload_resp = client.upload_file("document.pdf")
    file_id = upload_resp['file_id']
    print(f"File uploaded: {file_id}")

    # Submit job
    print("Submitting job...")
    job_resp = client.submit_job(
        file_id=file_id,
        output_format="markdown",
        processing_options={
            "dpi": 300,
            "prefer_quality": True
        }
    )
    job_id = job_resp['job_id']
    print(f"Job submitted: {job_id}")

    # Wait for completion
    print("Waiting for completion...")
    final_status = client.wait_for_completion(job_id)

    if final_status['status'] == 'completed':
        # Get result
        result = client.get_result(job_id)
        print(f"Processing complete! Took {result['result']['processing_time_seconds']:.1f}s")

        # Download
        client.download_result(job_id, "output.md")
        print("Result downloaded to output.md")
    else:
        print(f"Job failed: {final_status.get('error')}")
```

### With Custom Prompts

```python
# Submit job with custom prompts
job_resp = client.submit_job(
    file_id=file_id,
    model="qwen2-vl-7b",
    custom_prompts={
        "merge": """You are analyzing a legal document.
        Carefully merge these text versions, preserving legal terminology:
        Embedded: {embedded_text}
        OCR: {ocr_text}

        Return only the accurate merged text."""
    },
    output_format="markdown"
)
```

## Configuration Queries

### List Available Models

```bash
curl http://localhost:8000/api/v1/config/models | jq '.'
```

**Response:**
```json
{
  "models": [
    {
      "model_id": "qwen3-vl-8b",
      "name": "Qwen3-VL 8B",
      "description": "Highest quality, best for production",
      "capabilities": ["ocr", "markdown", "merge", "structured"],
      "estimated_memory_gb": 18.0,
      "default": false
    },
    {
      "model_id": "deepseek-ocr",
      "name": "DeepSeek-OCR",
      "description": "Specialized OCR model",
      "capabilities": ["ocr"],
      "estimated_memory_gb": 15.2,
      "default": true
    }
  ]
}
```

### List Prompt Types

```bash
curl http://localhost:8000/api/v1/config/prompts | jq '.'
```

### Get System Settings

```bash
curl http://localhost:8000/api/v1/config/settings | jq '.'
```

**Response:**
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

## File Management

### Get File Metadata

```bash
curl http://localhost:8000/api/v1/files/123e4567-e89b-12d3-a456-426614174000 | jq '.'
```

### Delete File

```bash
curl -X DELETE http://localhost:8000/api/v1/files/123e4567-e89b-12d3-a456-426614174000 | jq '.'
```

**Response:**
```json
{
  "file_id": "123e4567-e89b-12d3-a456-426614174000",
  "deleted": true
}
```

## Job Cancellation

```bash
curl -X DELETE http://localhost:8000/api/v1/process/jobs/987fcdeb-51a2-43f1-9876-123456789abc | jq '.'
```

**Response:**
```json
{
  "job_id": "987fcdeb-51a2-43f1-9876-123456789abc",
  "status": "cancelled",
  "message": "Job cancelled successfully"
}
```
