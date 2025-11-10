# Installation Guide

Detailed installation instructions for the OCR Service on Ubuntu WSL2 with dual RTX 4090s.

## Prerequisites

### Hardware
- NVIDIA GPU with 6GB+ VRAM (optimized for dual RTX 4090s)
- 16GB+ RAM recommended

### Software
- Ubuntu 22.04+ (tested on WSL2)
- Python 3.11+
- CUDA 12.4+ toolkit
- Git

## Step-by-Step Installation

### 1. Install System Dependencies

```bash
# Update package list
sudo apt update

# Install build essentials
sudo apt install -y build-essential git wget curl

# Install CUDA toolkit (if not already installed)
# For WSL2, follow: https://docs.nvidia.com/cuda/wsl-user-guide/index.html
```

### 2. Install UV Package Manager

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc  # or ~/.zshrc
```

### 3. Clone Repository

```bash
cd ~/code
# Replace with your actual repository URL
git clone <your-repo-url> ocr-service
cd ocr-service
```

### 4. Run Setup Script

The automated setup script will handle everything:

```bash
./scripts/setup.sh
```

This script will:
1. Create Python 3.11 virtual environment with UV
2. Install PyTorch 2.5.1 with CUDA 12.4 support
3. Install Transformers 4.46.3 (critical version!)
4. Install core dependencies
5. Build Flash-Attention from source (~5-10 minutes)
6. Create necessary directories
7. Copy environment template

**Note**: The script takes 10-15 minutes due to Flash-Attention compilation.

### 5. Verify Installation

```bash
source .venv/bin/activate
python scripts/verify_installation.py
```

This will check:
- Python version
- Package versions (especially Transformers 4.46.3!)
- CUDA availability
- GPU detection
- Flash-Attention installation
- Project structure

### 6. Configure Environment

```bash
# Copy and edit .env file
cp .env.example .env
nano .env  # or vim, code, etc.
```

Key settings to review:
```bash
DEFAULT_MODEL=qwen2-vl-7b              # Choose your default model
CUDA_VISIBLE_DEVICES=0,1               # Your GPU configuration
MAX_IMAGE_SIZE=4096                    # Maximum image dimension
```

### 7. Test the Installation

#### Quick Test
```bash
source scripts/quick_start.sh
ocr --help
ocr gpu
ocr models
```

#### Comprehensive Model Test
```bash
python examples/test_models.py
```

This will test all three models and verify they load correctly.

## Manual Installation (Alternative)

If the automated script doesn't work, follow these manual steps:

### 1. Create Virtual Environment

```bash
cd ~/code/ocr-service
uv venv --python 3.11
source .venv/bin/activate
```

### 2. Install PyTorch

```bash
uv pip install torch==2.5.1 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

### 3. Install Transformers (CRITICAL VERSION!)

```bash
uv pip install transformers==4.46.3 tokenizers==0.20.3 accelerate safetensors
```

⚠️ **CRITICAL**: Must be exactly 4.46.3, NOT 4.51.x or newer!

### 4. Install Core Dependencies

```bash
uv pip install -e .
```

### 5. Install Build Tools

```bash
uv pip install setuptools wheel ninja
```

### 6. Build Flash-Attention

```bash
# This takes 5-10 minutes
uv pip install flash-attn --no-build-isolation
```

### 7. Create Directories

```bash
mkdir -p data/{input,output,cache} logs
```

### 8. Setup Environment

```bash
cp .env.example .env
```

## Troubleshooting

### Flash-Attention Build Fails

**Error**: `nvcc not found` or compilation errors

**Solution**:
```bash
# Check CUDA toolkit
nvcc --version

# If missing, install CUDA toolkit for WSL2
# Follow: https://docs.nvidia.com/cuda/wsl-user-guide/index.html
```

**Error**: ABI mismatch or import errors

**Solution**: Must compile from source, don't use pre-built wheels
```bash
uv pip uninstall flash-attn
uv pip install flash-attn --no-build-isolation
```

### Wrong Transformers Version

**Error**: Model loading fails with import errors

**Solution**: Check version and downgrade if needed
```bash
# Check version
python -c "import transformers; print(transformers.__version__)"

# Should output: 4.46.3

# If wrong version, reinstall
uv pip uninstall transformers
uv pip install transformers==4.46.3
```

### CUDA Not Available

**Error**: `torch.cuda.is_available()` returns False

**Solution**:
```bash
# Check NVIDIA driver
nvidia-smi

# Check PyTorch CUDA
python -c "import torch; print(torch.version.cuda)"

# Reinstall PyTorch with correct CUDA version
uv pip uninstall torch torchvision torchaudio
uv pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu124
```

### Out of Memory Errors

**Error**: CUDA out of memory

**Solutions**:
1. Use smaller model: `--model qwen2-vl-2b`
2. Set environment variables:
```bash
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True,max_split_size_mb:96
export MALLOC_ARENA_MAX=2
```
3. Reduce max image size in `.env`

### Import Errors

**Error**: `No module named 'qwen_vl_utils'`

**Solution**:
```bash
uv pip install qwen-vl-utils
```

**Error**: `No module named 'fitz'`

**Solution**:
```bash
uv pip install PyMuPDF
```

## Environment Variables

For optimal performance on dual RTX 4090s, set these environment variables:

```bash
# Add to ~/.bashrc or ~/.zshrc
export CUDA_VISIBLE_DEVICES=0,1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True,max_split_size_mb:96
export MALLOC_ARENA_MAX=2
export TOKENIZERS_PARALLELISM=false
```

Or use the quick start script:
```bash
source scripts/quick_start.sh
```

## Upgrading

To upgrade the OCR service:

```bash
cd ~/code/ocr-service
git pull
source .venv/bin/activate
uv pip install -e . --upgrade

# Verify
python scripts/verify_installation.py
```

**Never upgrade Transformers beyond 4.46.3!**

## Uninstallation

```bash
cd ~/code/ocr-service
rm -rf .venv
cd ..
rm -rf ocr-service
```

Model weights in `~/.cache/huggingface` can be deleted separately if needed.

## Frontend BAML Setup

The web interface uses BAML for intelligent command orchestration with AI-powered tool calling.

### Prerequisites

- BAML CLI is already installed system-wide at `/home/jenner/.local/bin/baml-cli`
- Node.js 18+ and npm

### Environment Variables

Create `web/.env.local` with API keys:

```bash
# Copy and edit environment file
cd web

# Create .env.local with the following content:
cat > .env.local << EOF
# OpenAI API key for o4-mini and GPT-4o Mini models
OPENAI_API_KEY=sk-...

# Anthropic API key for Claude Haiku 4.5 and Sonnet 4.5 models
ANTHROPIC_API_KEY=sk-ant-...

# FastAPI backend URL
NEXT_PUBLIC_API_URL=http://localhost:8000
EOF
```

**Note**: Copy the API keys from the root `.env` file if you have them there.

### Generate BAML Client

```bash
cd web
npm install
npm run baml:generate
```

This generates TypeScript types and client functions in `web/baml_client/`.

### Verify Setup

```bash
cd web
npm run dev
```

The chat interface should now intelligently parse commands like:
- "Process this document"
- "Format pages 8-20 like page 3"
- "Parse pages 10-15 using high quality"

### BAML Configuration

The BAML configuration is in `web/baml_src/main.baml`:

**Features:**
- **Retry Policies**: StandardRetry (3 retries), AggressiveRetry (5 retries)
- **Fallback Clients**: o4-mini → Claude Sonnet 4.5 for reasoning
- **Streaming**: Real-time prompt refactoring progress
- **Models**: Claude Haiku 4.5 (fast), o4-mini (reasoning), GPT-4o Mini (validation)

**Cost Estimates:**
- Simple requests: ~$0.01/1K requests (Haiku only)
- Complex refactoring: ~$0.05/1K requests (o4-mini)
- Daily typical: ~$0.20-0.30 for 10K requests

## Next Steps

After successful installation:

1. **Test basic OCR**: `ocr examples/test_image.jpg`
2. **Run model tests**: `python examples/test_models.py`
3. **Start frontend**: `cd web && npm run dev`
4. **Read the README**: `README.md`
5. **Try examples**: Check `examples/` directory
6. **Start developing**: See `docs/` for API details

## Getting Help

If you encounter issues not covered here:

1. Check `scripts/verify_installation.py` output
2. Review the error messages carefully
3. Check GPU memory: `ocr gpu`
4. Verify versions: `ocr info`
5. Check logs in `logs/` directory

## Critical Version Requirements

| Package | Version | Notes |
|---------|---------|-------|
| Python | 3.11+ | Required |
| PyTorch | 2.5.1 | With CUDA 12.4 |
| Transformers | **>=4.57.0** | **Required for Qwen3-VL** |
| Tokenizers | **>=0.22.0** | Required by Transformers 4.57.0+ |
| qwen-vl-utils | 0.0.14 | Required for Qwen3-VL |
| Flash-Attention | 2.7.3+ | Must compile from source |
| CUDA | 12.4+ | Toolkit required |
| BAML | 0.213.0+ | For web interface orchestration |

**Note**: Transformers >=4.57.0 is required for Qwen3-VL support. This is compatible with DeepSeek-OCR.

