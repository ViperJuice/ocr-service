# Docker Container Setup

This directory contains Dockerfiles and inference servers for running OCR models in isolated containers.

## Architecture

```
┌─────────────────────────────────────────────┐
│  FastAPI Gateway (host, port 8000)         │
│  - Job queue                                │
│  - Pipeline orchestration                   │
│  - HTTP client to model containers          │
└─────────┬───────────────────────────────────┘
          │
    ┌─────┴─────────────────────┐
    │                           │
    ▼                           ▼
┌─────────────────┐    ┌─────────────────┐
│ DeepSeek-OCR    │    │  Qwen3-VL       │
│ Container       │    │  Container      │
│ Port 8001       │    │  Port 8002      │
│ GPU 0           │    │  GPU 0 (or 1)   │
│ transformers    │    │  transformers   │
│ 4.46.3          │    │  4.57.0+        │
└─────────────────┘    └─────────────────┘
```

## Why Docker?

1. **Dependency Isolation**: DeepSeek-OCR requires transformers==4.46.3, Qwen3-VL requires transformers>=4.57.0. These are incompatible.
2. **No Patches Needed**: Use official model releases without modifications
3. **Clean Architecture**: Matches sequential pipeline (OCR stage → Merge stage)
4. **Production Ready**: Standard containerization for deployment

## Containers

### DeepSeek-OCR Container

**Directory**: `deepseek/`

**Image**: `ocr-service/deepseek-ocr:latest`

**Dependencies**:
- CUDA 11.8
- Python 3.12
- transformers==4.46.3 (exact version for DeepSeek)
- torch==2.6.0
- flash-attn==2.7.3

**Port**: 8001

**Endpoints**:
- `GET /health` - Health check
- `GET /info` - Model information
- `POST /infer` - Run OCR inference

### Qwen3-VL Container

**Directory**: `qwen/`

**Image**: `ocr-service/qwen-vl:latest`

**Dependencies**:
- CUDA 12.1
- Python 3.11
- transformers>=4.57.0 (from source)
- qwen-vl-utils==0.0.14

**Port**: 8002

**Endpoints**:
- `GET /health` - Health check
- `GET /info` - Model information
- `POST /infer` - Run vision-language inference

## Building Containers

```bash
# Build both containers
docker-compose build

# Build individually
docker build -t ocr-service/deepseek-ocr:latest containers/deepseek/
docker build -t ocr-service/qwen-vl:latest containers/qwen/
```

## Running Containers

### Development (Single GPU)

```bash
# Start both containers
docker-compose up -d

# Check logs
docker-compose logs -f

# Check health
curl http://localhost:8001/health
curl http://localhost:8002/health

# Stop containers
docker-compose down
```

### Production (Multi-GPU)

Edit `docker-compose.yml` to assign different GPUs:

```yaml
services:
  deepseek:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['0', '1']  # GPUs 0-1

  qwen:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['2', '3']  # GPUs 2-3
```

## Testing Containers

### Test DeepSeek-OCR

```bash
# Health check
curl http://localhost:8001/health

# Model info
curl http://localhost:8001/info

# Inference test (requires base64-encoded image)
curl -X POST http://localhost:8001/infer \
  -H "Content-Type: application/json" \
  -d '{
    "image_base64": "<base64_image_data>",
    "prompt": "<image>\nFree OCR. ",
    "base_size": 1024,
    "image_size": 640,
    "crop_mode": true
  }'
```

### Test Qwen3-VL

```bash
# Health check
curl http://localhost:8002/health

# Model info
curl http://localhost:8002/info

# Inference test
curl -X POST http://localhost:8002/infer \
  -H "Content-Type: application/json" \
  -d '{
    "image_base64": "<base64_image_data>",
    "messages": [
      {"role": "user", "content": "<image>\nDescribe this image."}
    ],
    "max_new_tokens": 2048
  }'
```

## Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs deepseek
docker-compose logs qwen

# Check GPU availability
nvidia-smi

# Restart containers
docker-compose restart
```

### Model loading takes too long

- First startup downloads models (~10-20GB each)
- Models are cached in shared volume `model-cache`
- Subsequent starts are faster (~30-60s)

### Out of memory

- Reduce GPU allocation in docker-compose.yml
- Use smaller GPUs for each container
- Enable quantization in inference servers (future)

### Permission errors

```bash
# Fix docker permissions
sudo usermod -aG docker $USER
newgrp docker

# Fix NVIDIA runtime
sudo systemctl restart docker
```

## Performance

### Expected Timings

- **Container startup**: 5-10 seconds
- **Model loading** (first time): 60-120 seconds (downloads models)
- **Model loading** (cached): 20-40 seconds
- **Inference latency**: 1-3 seconds per page (same as native)
- **Overhead**: ~5% total processing time

### Memory Usage

- **DeepSeek-OCR**: ~12GB GPU memory (BF16)
- **Qwen3-VL**: ~16GB GPU memory (BF16)
- **Shared cache**: ~20-30GB disk space

## Development

### Modifying Inference Servers

1. Edit `deepseek/deepseek_inference_server.py` or `qwen/qwen_inference_server.py`
2. Rebuild container: `docker-compose build deepseek` (or `qwen`)
3. Restart: `docker-compose up -d --force-recreate deepseek`

### Adding New Endpoints

Add to `app` in inference server:

```python
@app.get("/custom-endpoint")
async def custom_endpoint():
    return {"message": "custom response"}
```

Rebuild and restart container.

## Migration Status

- [x] Dockerfiles created
- [x] Inference servers created
- [x] docker-compose.yml created
- [ ] HTTP client infrastructure (in progress)
- [ ] Model wrappers updated (pending)
- [ ] Pipeline integration (pending)
- [ ] End-to-end testing (pending)

## See Also

- [Main README](../README.md) - Project overview
- [CHANGELOG](../CHANGELOG.md) - Migration notes
- [docker-compose.yml](../docker-compose.yml) - Container configuration
