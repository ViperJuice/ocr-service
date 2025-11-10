#!/bin/bash
# Quick start script - sets environment and activates venv

# Set environment variables for optimal GPU usage
export CUDA_VISIBLE_DEVICES=0,1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True,max_split_size_mb:96
export MALLOC_ARENA_MAX=2
export TOKENIZERS_PARALLELISM=false

# Activate virtual environment
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    echo "✓ Virtual environment activated"
    echo "✓ Environment variables set for dual RTX 4090s"
    echo ""
    echo "Ready to use OCR service!"
    echo "  Try: ocr --help"
    echo "  Or:  ocr gpu (to check GPU status)"
else
    echo "Error: Virtual environment not found."
    echo "Please run ./scripts/setup.sh first"
    exit 1
fi

