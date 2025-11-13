FROM nvidia/cuda:11.8.0-runtime-ubuntu22.04

# Install Python 3.11 and dependencies (3.12 not available in Ubuntu 22.04 repos)
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    python3.11-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create symlink for python3.11 as python
RUN ln -s /usr/bin/python3.11 /usr/bin/python

# Install EXACT official DeepSeek dependencies (NO PATCHES)
RUN pip install --no-cache-dir torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu118
RUN pip install --no-cache-dir transformers==4.46.3 tokenizers==0.20.3
RUN pip install --no-cache-dir einops addict easydict pillow
RUN pip install --no-cache-dir 'accelerate>=0.26.0'
RUN pip install --no-cache-dir fastapi==0.100.0 uvicorn[standard]==0.23.0 pydantic

# Note: flash-attn requires compilation and devel image. Skipping for now - model works without it (just slower)
# For production, use nvidia/cuda:11.8.0-devel-ubuntu22.04 base image and install flash-attn

WORKDIR /app
COPY deepseek_inference_server.py /app/
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["uvicorn", "deepseek_inference_server:app", "--host", "0.0.0.0", "--port", "8001"]
