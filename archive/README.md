# Archive Directory

This directory contains historical files from the OCR service development process. These files are no longer used in the current architecture but are preserved for reference.

## Directory Structure

### `development-tests/`
Development and debugging test scripts from the migration to container-based architecture.

**Files:**
- `test_lazy_loading.py` - Tests for lazy model loading concept (pre-container)
- `test_lazy_loading_simple.py` - Simplified lazy loading test with HTTP client
- `test_qwen_container.py` - Simple single container test (superseded)
- `test_batch_simple.py` - Basic batch processing test (superseded)
- `test_event_loop_fix.py` - Event loop bug fix validation

**Historical Context:** These tests document the evolution from direct model loading to the current container-based architecture where the backend makes HTTP calls to DeepSeek and Qwen3 containers.

### `documentation/`
Obsolete documentation from previous architectural approaches.

**Files:**
- `PATCHES_QUICK_REF.md` - Documentation of the patch-based approach that was replaced by containerization

## Current Architecture

The current system uses:
- **Container-based inference**: DeepSeek-OCR and Qwen3-VL run in separate Docker containers
- **HTTP client communication**: Backend makes HTTP calls to containers (no direct model loading)
- **Lazy loading**: Models load on first request and auto-unload to free GPU memory
- **Staged pipeline**: OCR stage (all pages) → Merge stage (all pages) for optimal GPU usage

See the main project documentation for current architecture details:
- `/DOCKER_CONTAINERIZATION_SUMMARY.md` - Container architecture overview
- `/OPENAI_API_IMPLEMENTATION.md` - OpenAI-compatible API endpoints
- `/BATCH_INFERENCE_API.md` - Batch processing API documentation

## Cleanup Date
January 14, 2025

These files were archived as part of the Supabase migration preparation to clean up the repository and focus on current architecture testing.
