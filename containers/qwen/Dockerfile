FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

# Install Python 3.11 and dependencies
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    python3.11-dev \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create symlink for python3.11 as python
RUN ln -s /usr/bin/python3.11 /usr/bin/python

# Install Qwen3-VL dependencies (requires transformers from source)
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu121
RUN pip install --no-cache-dir git+https://github.com/huggingface/transformers
RUN pip install --no-cache-dir qwen-vl-utils==0.0.14
RUN pip install --no-cache-dir accelerate pillow
RUN pip install --no-cache-dir fastapi==0.100.0 uvicorn[standard]==0.23.0 pydantic

WORKDIR /app
COPY qwen_inference_server.py /app/
EXPOSE 8002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

CMD ["uvicorn", "qwen_inference_server:app", "--host", "0.0.0.0", "--port", "8002"]
