# OCR Service

Production-ready OCR service using vision-language models (Qwen3-VL, DeepSeek-OCR) optimized for dual RTX 4090 workstations.

## 🎯 Features

- **Multi-Model Support**: Qwen3-VL-8B (quality), Qwen3-VL-4B (intermediate), Qwen3-VL-2B (speed), DeepSeek-OCR (specialized)
- **Fast Processing**: 1-2 seconds per image on dual RTX 4090s
- **Multiple Formats**: Supports images (JPEG, PNG, TIFF) and PDFs
- **Output Options**: Text, Markdown, JSON
- **CLI & API**: Command-line tool and REST API (coming soon)
- **Optimized**: Uses Flash-Attention 2 for efficiency

## 📋 Requirements

- **Hardware**: NVIDIA GPU with 6GB+ VRAM (optimized for dual RTX 4090s)
- **OS**: Ubuntu 22.04+ (tested on WSL2)
- **Python**: 3.11+
- **CUDA**: 12.4+ (toolkit required for Flash-Attention)

## 🚀 Quick Start

### 1. Clone and Setup

```bash
cd ~/code
git clone <your-repo-url> ocr-service
cd ocr-service
```

### 2. Run Setup Script

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

This will:
- Create Python 3.11 virtual environment
- Install PyTorch 2.5.1 with CUDA support
- Install Transformers 4.57.0+ (required for Qwen3-VL!)
- Install all dependencies including qwen-vl-utils

⏱️ **Note**: Setup takes 5-10 minutes

### Optional: FlashAttention 2 Installation

FlashAttention 2 is **highly recommended** for memory efficiency (30-40% VRAM reduction) and speed (20-30% faster).

```bash
# Check if your system supports FlashAttention 2
python scripts/verify_flash_attention.py --check-prereqs

# Install FlashAttention 2 (takes 5-10 minutes)
./scripts/install_flash_attention.sh
```

If installation fails or your GPU doesn't support it (requires compute capability ≥7.5), the models will use standard attention automatically with slightly higher VRAM usage.

**For detailed instructions and troubleshooting**, see [specs/flash-attention-setup.md](specs/flash-attention-setup.md).

### 3. Activate Environment

```bash
source scripts/quick_start.sh
```

### 4. Test OCR

```bash
# Check GPU status
ocr gpu

# List available models
ocr models

# Run OCR on an image
ocr path/to/image.jpg

# Save output
ocr image.jpg --output result.txt

# Use specific model
ocr image.jpg --model qwen3-vl-2b --format markdown
```

## 📖 Usage

### Command-Line Interface

#### Single Image OCR

```bash
# Basic usage
ocr image.jpg

# With specific model and output
ocr document.png --model deepseek-ocr --output result.md --format markdown

# Skip preprocessing
ocr scan.jpg --no-preprocess
```

#### PDF Processing (with Hybrid Intelligence)

The PDF command automatically detects embedded text and uses AI to merge it with OCR for maximum accuracy:

```bash
# Automatic hybrid processing (default)
ocr pdf document.pdf --output result.txt

# Process with specific method
ocr pdf document.pdf -o result.txt --method hybrid    # AI-powered merge
ocr pdf scan.pdf -o result.txt --method ocr           # OCR only (for scanned PDFs)
ocr pdf text.pdf -o result.txt --method extract       # Text extraction only (fastest)

# Limit pages and show details
ocr pdf large.pdf -o result.txt --max-pages 10 --verbose

# Force OCR even if embedded text exists
ocr pdf document.pdf -o result.txt --force-ocr

# Low DPI for memory-constrained processing
ocr pdf document.pdf -o result.txt --dpi 100
```

**Hybrid Processing**: When a PDF has embedded text, the system:
1. Extracts the embedded text directly
2. Renders the page and runs OCR
3. Uses the AI model to intelligently merge both sources
4. Produces the most accurate result possible

#### GPU Loading Strategies

The OCR service automatically detects the optimal GPU loading strategy based on your hardware:

**Auto-Detection (default - recommended):**

```bash
ocr pdf document.pdf -o output.txt
```

The auto-detection follows this priority:

1. **Single-GPU Persistent** - Load both models on one GPU (best latency)
2. **Dual-GPU Persistent** - Load models on separate GPUs (when they don't fit together)
3. **Sharded Multi-GPU** - Split large models across GPUs
4. **Sequential** - Load/unload models as needed (limited VRAM)

**Manual Strategy Selection:**

Force dual-GPU (requires 2 GPUs):

```bash
ocr pdf document.pdf -o output.txt --gpu-strategy dual
```

Force sequential (single GPU, swap models):

```bash
ocr pdf document.pdf -o output.txt --gpu-strategy sequential
```

Force sharded (split large models across GPUs):

```bash
ocr pdf document.pdf -o output.txt --gpu-strategy sharded
```

**Performance Tips:**

- Use `auto` for optimal performance (recommended)
- Single-GPU persistent has the lowest latency when both models fit
- Dual-GPU is best when models don't fit together on one GPU
- Sequential is slowest but works with limited VRAM

#### Utility Commands

```bash
# Show available models
ocr models

# Check GPU status and memory
ocr gpu

# Show system information
ocr info
```

### Python API

```python
from PIL import Image
from config.settings import get_settings
from src.models import ModelManager

# Initialize
settings = get_settings()
model_configs = settings.load_model_configs()
manager = ModelManager(model_configs["models"])

# Load model
manager.load_model("qwen3-vl-8b")

# Process image
image = Image.open("document.jpg")
result = manager.get_current_model().process_image(image)

print(result.text)
print(f"Processing time: {result.processing_time:.2f}s")
```

## 🔧 Configuration

Edit `.env` file to customize:

```bash
# Model selection
DEFAULT_MODEL=qwen3-vl-8b              # qwen3-vl-8b, qwen3-vl-4b, qwen3-vl-2b, deepseek-ocr

# GPU configuration (dual RTX 4090 optimized)
CUDA_VISIBLE_DEVICES=0,1
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True,max_split_size_mb:96

# Processing limits
MAX_IMAGE_SIZE=4096
MAX_UPLOAD_SIZE_MB=50
```

## 📊 Model Comparison

| Model | VRAM | Speed | Quality | Best For |
|-------|------|-------|---------|----------|
| **Qwen3-VL-8B** | 15GB | ~2s | ⭐⭐⭐⭐⭐ | Production, highest quality, 32 languages |
| **Qwen3-VL-4B** | 9GB | ~1.5s | ⭐⭐⭐⭐½ | Balanced quality/speed |
| **Qwen3-VL-2B** | 5GB | ~1s | ⭐⭐⭐⭐ | High throughput, fast |
| **DeepSeek-OCR** | 6GB | ~1.5s | ⭐⭐⭐⭐⭐ | OCR-specialized tasks |

All models tested on dual RTX 4090s (48GB total VRAM).

## ⚠️ Critical Setup Notes

### Transformers Version

**MUST** use Transformers 4.57.0+ for Qwen3-VL support.

```bash
# Correct version
uv pip install transformers>=4.57.0

# Qwen3-VL requires transformers 4.57.0 or newer
```

### DeepSeek-OCR Compatibility Patches

DeepSeek-OCR requires compatibility patches for transformers 4.57.1+. These patches are **automatically applied** the first time you load the DeepSeek-OCR model.

**What gets patched:**
- Attention mask API (`_prepare_4d_causal_attention_mask` → `create_causal_mask`)
- DynamicCache API changes (`seen_tokens`, `get_max_length`, `get_usable_length`)
- LlamaAttention compatibility (RoPE position embeddings)
- Flash Attention 2 import compatibility
- Attention return value unpacking (MLA vs MHA modes)

**Patch scripts:**
- [`patch_deepseek_model.sh`](patch_deepseek_model.sh) - Main automated patch script
- [`fix_attention_mask.py`](fix_attention_mask.py) - Fixes attention mask preparation
- [`fix_attention_return.py`](fix_attention_return.py) - Handles attention return values

**Manual patching (if needed):**

If you need to re-apply patches (e.g., after HuggingFace re-downloads the model):

```bash
chmod +x patch_deepseek_model.sh
./patch_deepseek_model.sh
```

The patches are idempotent and safe to run multiple times.

**Performance Note:** The RoPE position embeddings patch actually **improves performance** by computing position embeddings once per forward pass (shared across layers) instead of per-layer.

### Flash-Attention

Must be compiled from source for your specific PyTorch version:

```bash
uv pip install flash-attn --no-build-isolation
```

Pre-compiled wheels will cause ABI mismatch errors.

### Environment Variables

Required for optimal GPU memory usage:

```bash
export CUDA_VISIBLE_DEVICES=0,1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True,max_split_size_mb:96
export MALLOC_ARENA_MAX=2
```

Add these to your `~/.bashrc` or `~/.zshrc` for persistence.

## 🐛 Troubleshooting

### ImportError: No module named 'qwen_vl_utils'

```bash
uv pip install qwen-vl-utils
```

### Flash-Attention build fails

Ensure CUDA toolkit is installed:

```bash
nvcc --version  # Should show CUDA 12.4+
```

If missing, install CUDA toolkit for WSL2.

### Out of memory errors

Try a smaller model:

```bash
ocr image.jpg --model qwen3-vl-2b  # Only 5GB VRAM
```

### Model loading is slow

First-time model download can take several minutes. Models are cached in `~/.cache/huggingface`.

## 🌐 Web Interface

A modern, chat-based web interface is available for easy document processing:

### Quick Start

```bash
# Terminal 1: Start the API backend
source .venv/bin/activate
./scripts/start_api.sh

# Terminal 2: Start the web interface
cd web
npm install
npm run dev
```

Then open [http://localhost:3000](http://localhost:3000) in your browser.

### Features

- 💬 **Chat Interface** - Natural language commands ("Parse the whole document")
- 🎨 **Dark Theme** - Beautiful Obsidian/BetterStack-inspired UI
- 📊 **Real-Time Progress** - Live SSE-powered progress updates
- 🤖 **BAML Prompting** - Intelligent prompt management with type safety
- 📄 **Multi-Format Display** - View results as Markdown, JSON, or text
- 📥 **Export Options** - Download or save to Google Drive

### Documentation

See [web/README.md](web/README.md) for detailed web interface documentation.

## 📚 Documentation

### Setup & Installation
- [Installation Guide](docs/INSTALLATION.md) - Complete setup instructions for new servers
- [DeepSeek-OCR Patches](docs/DEEPSEEK_OCR_PATCHES.md) - Transformers 4.57.1 compatibility details
- [Flash Attention Setup](specs/flash-attention-setup.md) - Flash Attention 2 installation guide

### API & Usage
- [API Reference](docs/API_REFERENCE.md) - Complete REST API documentation
- [Model Guide](docs/MODELS.md) - Detailed model comparison
- [Configuration](docs/CONFIGURATION.md) - All configuration options

### Deployment
- [Deployment Guide](docs/DEPLOYMENT.md) - Production deployment guide
- [Web Interface](web/README.md) - Frontend documentation

## 🧪 Development

### Install Development Dependencies

```bash
uv pip install -e ".[dev]"
```

### Run Tests

```bash
pytest tests/
```

### Code Formatting

```bash
black src/ tests/
ruff check src/ tests/
```

## 📝 Examples

See `examples/` directory for:
- `basic_usage.py` - Simple OCR example
- `batch_processing.py` - Process multiple files
- `api_client.py` - API usage (coming soon)

## 🙏 Credits

Built with:
- [Qwen3-VL](https://github.com/QwenLM/Qwen3-VL) - Vision-language models by Alibaba (enhanced 32-language OCR, 256K context)
- [DeepSeek-OCR](https://github.com/deepseek-ai/DeepSeek-OCR) - OCR-specialized model by DeepSeek
- [Transformers](https://github.com/huggingface/transformers) - HuggingFace Transformers
- [Flash-Attention](https://github.com/Dao-AILab/flash-attention) - Efficient attention implementation

## 📄 License

MIT License - See LICENSE file for details

## 🤝 Contributing

Contributions are welcome! Please open an issue or submit a pull request.

---

**Version**: 0.1.0  
**Status**: Phase 1 Complete ✅

