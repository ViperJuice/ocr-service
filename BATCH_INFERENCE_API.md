# Batch Inference API

## Overview

Both DeepSeek-OCR and Qwen3-VL containers now support batch inference, allowing multiple images to be processed in a single request with the model staying loaded throughout the entire batch.

## Key Benefits

1. **Model Persistence**: Model loads once and stays loaded for entire batch
2. **Auto-Unload**: Optionally unload model after batch completes
3. **Error Resilience**: Individual item failures don't stop batch processing
4. **Performance**: Eliminates model load/unload overhead between images
5. **Progress Tracking**: Each result includes index for mapping back to original request

## API Endpoints

### DeepSeek-OCR Batch Inference

**Endpoint**: `POST /batch_infer`

**Request Schema**:
```json
{
  "items": [
    {
      "image_base64": "string",
      "prompt": "string",
      "base_size": 1024,
      "image_size": 640,
      "crop_mode": true,
      "eval_mode": true
    }
  ],
  "gpu_ids": [0],  // Optional: specify GPUs
  "auto_unload": true  // Default: true
}
```

**Response Schema**:
```json
{
  "results": [
    {
      "text": "string",
      "success": true,
      "error": null,
      "index": 0
    }
  ],
  "total_items": 10,
  "successful_items": 9,
  "failed_items": 1,
  "batch_success": false,  // true only if ALL items succeeded
  "model_unloaded": true  // Whether auto-unload executed
}
```

### Qwen3-VL Batch Inference

**Endpoint**: `POST /batch_infer`

**Request Schema**:
```json
{
  "items": [
    {
      "image_base64": "string",
      "messages": [
        {
          "role": "user",
          "content": "<image> Describe this image."
        }
      ],
      "max_new_tokens": 2048
    }
  ],
  "gpu_ids": [0],  // Optional: specify GPUs
  "auto_unload": true  // Default: true
}
```

**Response Schema**:
```json
{
  "results": [
    {
      "text": "string",
      "success": true,
      "error": null,
      "index": 0
    }
  ],
  "total_items": 10,
  "successful_items": 10,
  "failed_items": 0,
  "batch_success": true,
  "model_unloaded": true
}
```

## Usage Examples

### Python with httpx

```python
import httpx
import base64
from pathlib import Path

async def batch_process_deepseek(image_paths: list[Path]):
    """Process multiple images with DeepSeek-OCR in one batch"""

    # Prepare batch items
    items = []
    for img_path in image_paths:
        with open(img_path, 'rb') as f:
            img_b64 = base64.b64encode(f.read()).decode('utf-8')

        items.append({
            "image_base64": img_b64,
            "prompt": "Extract all text from this document.",
            "base_size": 1024,
            "image_size": 640
        })

    # Send batch request
    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(
            "http://localhost:8001/batch_infer",
            json={
                "items": items,
                "auto_unload": True  # Unload model after batch
            }
        )
        result = response.json()

    # Process results
    print(f"Batch complete: {result['successful_items']}/{result['total_items']} succeeded")

    for item in result['results']:
        if item['success']:
            print(f"Image {item['index']}: {len(item['text'])} chars extracted")
        else:
            print(f"Image {item['index']}: FAILED - {item['error']}")

    return result
```

### Python with httpx - Qwen Batch

```python
async def batch_process_qwen(image_paths: list[Path]):
    """Process multiple images with Qwen3-VL in one batch"""

    # Prepare batch items
    items = []
    for img_path in image_paths:
        with open(img_path, 'rb') as f:
            img_b64 = base64.b64encode(f.read()).decode('utf-8')

        items.append({
            "image_base64": img_b64,
            "messages": [
                {
                    "role": "user",
                    "content": "<image> Provide a detailed description of this image."
                }
            ],
            "max_new_tokens": 1024
        })

    # Send batch request
    async with httpx.AsyncClient(timeout=600.0) as client:
        response = await client.post(
            "http://localhost:8002/batch_infer",
            json={
                "items": items,
                "auto_unload": True
            }
        )
        result = response.json()

    return result
```

### Using HTTP Client Manager

```python
from src.models.http_client_manager import HTTPClientManager, ModelType

async def process_batch_via_manager(image_paths: list[Path]):
    """Process batch using HTTP client manager"""

    async with HTTPClientManager() as manager:
        # Prepare DeepSeek batch
        deepseek_items = [
            {
                "image_base64": base64.b64encode(open(p, 'rb').read()).decode(),
                "prompt": "Extract text",
                "base_size": 1024
            }
            for p in image_paths
        ]

        # Send batch request
        client = manager.clients[ModelType.DEEPSEEK_OCR]
        response = await client.post(
            "/batch_infer",
            json={
                "items": deepseek_items,
                "auto_unload": True
            },
            timeout=300.0
        )
        result = response.json()

        print(f"Processed {result['successful_items']} images")
        return result
```

## Workflow Patterns

### Pattern 1: Auto-Unload After Batch (Recommended)

```python
# Process batch with auto-unload
result = await batch_process_deepseek(images)
# Model automatically unloaded, GPU memory freed
```

### Pattern 2: Manual Unload Control

```python
# Process batch WITHOUT auto-unload
result = await client.post("/batch_infer", json={
    "items": items,
    "auto_unload": False  # Keep model loaded
})

# Do more work with the same model...

# Manually unload when done
await client.post("/unload")
```

### Pattern 3: Sequential Batches

```python
# Batch 1: Process first set of images
batch1 = await client.post("/batch_infer", json={
    "items": items1,
    "auto_unload": False  # Keep model loaded
})

# Batch 2: Process second set (model already loaded)
batch2 = await client.post("/batch_infer", json={
    "items": items2,
    "auto_unload": True  # Unload after this batch
})
```

## Error Handling

### Partial Batch Failure

If some items fail, the batch continues processing:

```python
result = await batch_process_deepseek(images)

# Check overall success
if result['batch_success']:
    print("All items succeeded!")
else:
    print(f"{result['failed_items']} items failed")

    # Process errors
    for item in result['results']:
        if not item['success']:
            print(f"Item {item['index']} failed: {item['error']}")
```

### Complete Batch Failure

If model loading fails, batch returns with no results:

```python
try:
    result = await batch_process_deepseek(images)
    if result['successful_items'] == 0:
        print("Batch completely failed - check logs")
except httpx.HTTPError as e:
    print(f"HTTP error: {e}")
```

## Performance Considerations

### Batch Size Recommendations

- **DeepSeek-OCR**: 10-50 images per batch (depends on image size)
- **Qwen3-VL**: 5-20 images per batch (more memory intensive)

### Memory Management

```python
# Monitor GPU memory before large batches
info = await client.get("http://localhost:8001/info")
gpu_free = info.json()['gpu_memory'][0]['free']

if gpu_free < 2000:  # Less than 2GB free
    print("WARNING: Low GPU memory, consider smaller batch")
```

### Timeout Settings

```python
# Increase timeout for large batches
async with httpx.AsyncClient(timeout=600.0) as client:  # 10 minutes
    result = await client.post("/batch_infer", json={"items": large_batch})
```

## Comparison: Single vs Batch

**Single Inference** (10 images):
```
Load model → Process image 1 → Unload
Load model → Process image 2 → Unload
Load model → Process image 3 → Unload
... (10 load/unload cycles)
```

**Batch Inference** (10 images):
```
Load model → Process all 10 images → Unload
(1 load/unload cycle)
```

**Performance Gain**: ~5-10x faster for batches of 10+ images

## Integration with Sequential Pipeline

```python
async def process_document_batch(pdf_pages: list[Path]):
    """
    Process multiple PDF pages through sequential pipeline
    Stage 1: DeepSeek batch → Stage 2: Qwen batch
    """

    async with HTTPClientManager() as manager:
        # Stage 1: DeepSeek OCR (batch)
        deepseek_result = await manager.clients[ModelType.DEEPSEEK_OCR].post(
            "/batch_infer",
            json={
                "items": [{"image_base64": encode_image(p), "prompt": "OCR"}
                         for p in pdf_pages],
                "auto_unload": True  # Free memory for Stage 2
            }
        )

        extracted_texts = [r['text'] for r in deepseek_result.json()['results']]

        # Stage 2: Qwen refinement (batch)
        qwen_result = await manager.clients[ModelType.QWEN_VL].post(
            "/batch_infer",
            json={
                "items": [{
                    "image_base64": encode_image(p),
                    "messages": [{
                        "role": "user",
                        "content": f"<image> Refine this OCR: {text}"
                    }]
                } for p, text in zip(pdf_pages, extracted_texts)],
                "auto_unload": True  # Free memory after pipeline
            }
        )

        return qwen_result.json()
```

## Status Codes

- **200**: Batch processed (check `batch_success` for individual failures)
- **503**: Model failed to load
- **422**: Invalid request schema
- **500**: Server error
