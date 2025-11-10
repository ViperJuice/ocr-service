#!/bin/bash
# Startup script for OCR Service API

# Set working directory to project root
cd "$(dirname "$0")/.."

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Default values
HOST="${OCR_API_HOST:-0.0.0.0}"
PORT="${OCR_API_PORT:-8000}"
WORKERS="${OCR_API_WORKERS:-1}"
RELOAD="${OCR_API_RELOAD:-false}"

echo "Starting OCR Service API..."
echo "  Host: $HOST"
echo "  Port: $PORT"
echo "  Workers: $WORKERS"
echo "  Reload: $RELOAD"

# Start API server
if [ "$RELOAD" = "true" ]; then
    # Development mode with auto-reload
    uvicorn src.api.main:app \
        --host "$HOST" \
        --port "$PORT" \
        --reload \
        --log-level info
else
    # Production mode
    uvicorn src.api.main:app \
        --host "$HOST" \
        --port "$PORT" \
        --workers "$WORKERS" \
        --log-level info
fi
