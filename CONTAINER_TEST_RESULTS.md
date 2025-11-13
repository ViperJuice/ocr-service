# OCR Service Container Test Results

## Summary
Both DeepSeek-OCR and Qwen3-VL containers are successfully containerized and tested.

## Container Status

### DeepSeek-OCR Container
- **Image**: `ocr-service/deepseek-ocr:latest` (13.4GB)
- **Port**: 8001
- **Status**: ✅ Healthy and working
- **GPU**: CUDA device (GPU 0)
- **Model Version**: deepseek-ai/DeepSeek-OCR @ revision 1e3401a (with masked_scatter fix)

### Qwen3-VL Container
- **Image**: `ocr-service/qwen-vl:latest` (12.8GB)
- **Port**: 8002
- **Status**: ✅ Healthy and working
- **GPU**: CUDA device (GPU 0)
- **Model Version**: Qwen/Qwen3-VL-8B-Instruct

## Test Results

### DeepSeek-OCR (Port 8001)

**Endpoint**: `/infer`

**Request**:
```json
{
  "image_base64": "<base64_encoded_image>",
  "prompt": "Extract all text from this image.",
  "base_size": 1024,
  "image_size": 640,
  "crop_mode": true
}
```

**Response**:
```json
{
  "text": "TestOCR\n\nThisisa simple test",
  "success": true,
  "error": null
}
```

**Parameters Used**:
- `base_size=1024` (official)
- `image_size=640` (official - NOT 1024!)
- `crop_mode=True` (official)
- `eval_mode=True` (critical for text return)

### Qwen3-VL (Port 8002)

**Endpoint**: `/infer`

**Request**:
```json
{
  "image_base64": "<base64_encoded_image>",
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "Extract all text from this image."}
      ]
    }
  ]
}
```

**Response**:
```json
{
  "text": "<model_generated_text>",
  "success": true,
  "error": null
}
```

## Available Endpoints

Both containers support:
- `GET /health` - Health check
- `GET /info` - Model information
- `POST /infer` - Single image inference
- `POST /batch_infer` - Batch processing
- `POST /v1/chat/completions` - OpenAI-compatible endpoint
- `POST /unload` - Unload model from GPU

## Key Differences

### DeepSeek-OCR
- Specialized OCR model
- Simple prompt format: `image_base64` + `prompt`
- More direct OCR extraction
- Requires specific parameters: base_size=1024, image_size=640

### Qwen3-VL
- General vision-language model
- Chat-based format: `image_base64` + `messages`
- More conversational responses
- Can provide additional context and formatting

## Docker Compose Usage

```bash
# Start both containers
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f deepseek
docker compose logs -f qwen

# Stop containers
docker compose down

# Rebuild after code changes
docker compose build
docker compose up -d
```

## GPU Configuration

Currently both containers share GPU 0. For production with multiple GPUs, see the commented section in `docker-compose.yml`:

```yaml
# Multi-GPU production example:
# DeepSeek: GPUs 0-1
# Qwen: GPUs 2-3
```

## Critical Fixes Applied

### DeepSeek-OCR Container
1. **Model Revision Pinning**: Using commit `1e3401a` with partial masked_scatter fix
2. **Runtime CUDA Patch**: Extends MPS fix to CUDA devices using row-wise assignment
3. **Official Parameters**: base_size=1024, image_size=640 (not 1024!)
4. **eval_mode=True**: Required for text return values

### Qwen3-VL Container
- Uses official `Qwen3VLForConditionalGeneration` model class
- Model: Qwen/Qwen3-VL-8B-Instruct
- flash_attention_2 for performance acceleration
- No patches needed

## Testing

```bash
# Test DeepSeek
python test_with_official_params.py

# Test Qwen
python test_qwen_container.py

# Test all endpoints
python test_all_endpoints.py
```

## Health Checks

Both containers have automatic health checks that verify:
- HTTP server is responsive
- Model loading capability
- GPU availability

Health check interval: 30s
Startup grace period: 120s (allows time for model download)

## Model Caching

Both containers share a Docker volume for HuggingFace model cache:
```yaml
volumes:
  model-cache:
    driver: local
```

This means models are downloaded once and shared between container restarts.

## Container Startup Time

- **First Run**: 2-5 minutes (downloading models)
- **Subsequent Runs**: 30-60 seconds (loading from cache)
- **With GPU Preloading**: Ready immediately for inference
