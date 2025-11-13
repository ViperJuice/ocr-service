# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - 2025-01-12

### Changed
- **BREAKING: Migrated to Docker-based model execution**
  - DeepSeek-OCR now runs in isolated container with transformers==4.46.3
  - Qwen3-VL now runs in isolated container with transformers>=4.57.0
  - Resolves dependency conflicts without patches
  - Uses official model releases (NO PATCHES)
  - Sequential container execution matches pipeline architecture
  - Added HTTP-based model inference via FastAPI containers
  - Files added:
    - `containers/deepseek/Dockerfile` - DeepSeek-OCR container
    - `containers/deepseek/deepseek_inference_server.py` - DeepSeek API server
    - `containers/qwen/Dockerfile` - Qwen3-VL container
    - `containers/qwen/qwen_inference_server.py` - Qwen API server
    - `docker-compose.yml` - Container orchestration
    - `src/models/http_client_manager.py` - HTTP client management (pending)

### Removed
- **Removed broken patch files** (2025-01-12)
  - Deleted `patch_deepseek_model.sh` - Caused triple rotary embedding initialization
  - Deleted `fix_attention_mask.py` - No longer needed with container isolation
  - Deleted `fix_attention_return.py` - No longer needed with container isolation
  - Cleared corrupted HuggingFace cache for DeepSeek-OCR
  - Reason: Patches caused model corruption:
    - Table hallucinations in OCR output
    - Triple rotary_emb initialization (modeling_deepseekv2.py lines 1488-1500)
    - Broken position_ids extension logic (lines 1614-1625)
    - Corrupted attention mask computation
  - Solution: Use official models in Docker containers with correct transformers versions

### Fixed
- **Critical: Fixed DeepSeek-OCR table hallucination bug**
  - Root cause: Broken patches corrupted model inference
  - Triple rotary embedding initialization caused position encoding errors
  - Wrong position_ids extension logic created dimension mismatches
  - Result: Model generated empty table structures instead of text
  - Solution: Removed all patches, use official model in Docker container

## [0.1.0] - 2025-01-11

### Added
- Initial implementation of OCR service with Qwen3-VL and DeepSeek-OCR support
- REST API with FastAPI backend
- Next.js 16 web interface with BAML integration
- Two-stage OCR pipeline (DeepSeek-OCR + Qwen3-VL refinement)
- Real-time system monitoring and progress tracking
- Batch processing with concurrent job management
- Natural language command parsing via BAML
- Page range extraction and selective processing

### Fixed
- DeepSeek-OCR compatibility with transformers 4.57.1+
  - Attention mask API changes
  - DynamicCache API changes
  - Flash Attention 2 compatibility
  - RoPE position embeddings
  - LlamaAttention integration

### Documentation
- Comprehensive installation guide
- DeepSeek-OCR patches documentation
- API reference and examples
- Web interface README

---

## Version History

- **v0.1.0** (2025-01-11): Initial release with dual-model OCR support
- **Unreleased** (2025-01-12): Critical fixes for vision embedding handling
