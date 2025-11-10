# Installation Guide

Complete installation instructions for setting up the OCR service on a new server.

## Prerequisites

### Hardware Requirements
- NVIDIA GPU with 6GB+ VRAM
- Recommended: Dual RTX 4090s (48GB total VRAM)
- CPU: 8+ cores recommended
- RAM: 16GB+ system memory
- Storage: 50GB+ free space for models

### Software Requirements
- **OS:** Ubuntu 22.04+ (tested on Ubuntu 22.04 WSL2)
- **Python:** 3.11 or newer
- **CUDA:** 12.4+ (required for Flash Attention 2)
- **Git:** For cloning repository

## Step-by-Step Installation

### 1. Install System Dependencies

```bash
# Update package list
sudo apt-get update

# Install Python 3.11
sudo apt-get install -y python3.11 python3.11-venv python3.11-dev

# Install build essentials (required for Flash Attention compilation)
sudo apt-get install -y build-essential gcc g++ make

# Install CUDA toolkit (if not already installed)
# See: https://developer.nvidia.com/cuda-downloads
# Example for Ubuntu 22.04:
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt-get update
sudo apt-get install -y cuda-toolkit-12-4

# Verify CUDA installation
nvcc --version  # Should show CUDA 12.4+
nvidia-smi      # Should show your GPUs
```

### 2. Install uv (Modern Python Package Manager)

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Add to PATH (add this to ~/.bashrc or ~/.zshrc)
export PATH="$HOME/.cargo/bin:$PATH"

# Reload shell
source ~/.bashrc  # or source ~/.zshrc
```

### 3. Clone Repository

```bash
cd ~/code
git clone <your-repo-url> ocr-service
cd ocr-service
```

### 4. Create Virtual Environment and Install Dependencies

```bash
# Create Python 3.11 virtual environment
uv venv --python 3.11

# Activate virtual environment
source .venv/bin/activate

# Install PyTorch with CUDA support
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# Install transformers 4.57.1+ (REQUIRED for Qwen3-VL)
uv pip install transformers>=4.57.1

# Install all other dependencies
uv pip install -r requirements.txt

# Install qwen-vl-utils (required for Qwen3-VL)
uv pip install qwen-vl-utils
```

### 5. Install Flash Attention 2 (Optional but Recommended)

Flash Attention 2 provides:
- 30-40% VRAM reduction
- 20-30% speed improvement
- Required GPU compute capability ≥ 7.5

```bash
# Check if your GPU supports Flash Attention 2
python scripts/verify_flash_attention.py --check-prereqs

# If supported, install Flash Attention 2
# This takes 5-10 minutes to compile
uv pip install flash-attn --no-build-isolation

# Verify installation
python -c "import flash_attn; print('Flash Attention 2 installed successfully')"
```

**Note:** If Flash Attention 2 installation fails, the models will automatically fall back to standard attention with slightly higher VRAM usage. This is acceptable for most use cases.

### 6. Set Environment Variables

Create a `.env` file in the project root:

```bash
# Copy example environment file
cp .env.example .env

# Edit .env file
nano .env
```

Add these critical environment variables:

```bash
# Model selection
DEFAULT_MODEL=qwen3-vl-8b

# GPU configuration
CUDA_VISIBLE_DEVICES=0,1
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True,max_split_size_mb:96

# Memory optimization
MALLOC_ARENA_MAX=2

# Processing limits
MAX_IMAGE_SIZE=4096
MAX_UPLOAD_SIZE_MB=50
```

**Add to shell profile for persistence:**

```bash
# Add to ~/.bashrc or ~/.zshrc
echo 'export CUDA_VISIBLE_DEVICES=0,1' >> ~/.bashrc
echo 'export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True,max_split_size_mb:96' >> ~/.bashrc
echo 'export MALLOC_ARENA_MAX=2' >> ~/.bashrc

# Reload shell
source ~/.bashrc
```

### 7. Verify Installation

```bash
# Activate environment
source .venv/bin/activate

# Check GPU status
ocr gpu

# List available models
ocr models

# Test with a sample image
ocr tests/api/fixtures/sample.pdf --model qwen3-vl-4b
```

Expected output:
```
Available GPUs:
  GPU 0: NVIDIA GeForce RTX 4090 (24GB)
  GPU 1: NVIDIA GeForce RTX 4090 (24GB)

Loading Qwen3-VL-4B model...
✓ Model loaded successfully
Processing time: 11.15s
[extracted text...]
```

## DeepSeek-OCR Compatibility Patches

**IMPORTANT:** DeepSeek-OCR requires compatibility patches for transformers 4.57.1+

### Automatic Patching (Recommended)

Patches are **automatically applied** when you first load DeepSeek-OCR:

```bash
# First time loading DeepSeek-OCR
ocr image.jpg --model deepseek-ocr
```

You'll see:
```
Loading DeepSeek-OCR model...
  Applying transformers 4.57.1 compatibility patches...
  ✓ Fixed attention mask code in modeling_deepseekv2.py
  ✓ Fixed attention return value unpacking in modeling_deepseekv2.py
  ✓ Compatibility patches applied
✓ Model loaded successfully
```

### Manual Patching (If Needed)

If automatic patching fails or you need to re-apply patches:

```bash
# Make script executable
chmod +x patch_deepseek_model.sh

# Run patch script
./patch_deepseek_model.sh
```

### Verify Patches Applied

```bash
# Run DeepSeek-OCR test
uv run python test_deepseek_ocr.py
```

Expected output:
```
✓ SUCCESS! DeepSeek-OCR fully working with transformers 4.57.1!
```

**For detailed information about the patches, see:** [docs/DEEPSEEK_OCR_PATCHES.md](DEEPSEEK_OCR_PATCHES.md)

## Common Installation Issues

### Issue: CUDA not found

**Symptom:** `nvcc: command not found` or `CUDA not available`

**Solution:**
```bash
# Install CUDA toolkit
sudo apt-get install cuda-toolkit-12-4

# Add to PATH
echo 'export PATH=/usr/local/cuda-12.4/bin:$PATH' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH=/usr/local/cuda-12.4/lib64:$LD_LIBRARY_PATH' >> ~/.bashrc
source ~/.bashrc
```

### Issue: Flash Attention build fails

**Symptom:** Compilation errors during `pip install flash-attn`

**Solution:**
```bash
# Ensure CUDA toolkit is installed
nvcc --version

# Ensure build tools are installed
sudo apt-get install build-essential gcc g++ make

# Try installing with no-build-isolation flag
uv pip install flash-attn --no-build-isolation

# If still fails, skip Flash Attention (models will use standard attention)
# Performance impact is acceptable for most use cases
```

### Issue: Out of memory errors

**Symptom:** `CUDA out of memory` during model loading or inference

**Solutions:**

**1. Use a smaller model:**
```bash
ocr image.jpg --model qwen3-vl-2b  # Only 5GB VRAM
```

**2. Reduce processing resolution:**
```bash
ocr pdf document.pdf --dpi 100  # Lower DPI = less memory
```

**3. Use sequential GPU strategy:**
```bash
ocr pdf document.pdf --gpu-strategy sequential
```

**4. Enable memory optimization:**
```bash
# Add to .env
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True,max_split_size_mb:96
```

### Issue: Model download is slow

**Symptom:** First model load takes a very long time

**Solution:**
- Models are large (2B: ~5GB, 4B: ~9GB, 8B: ~15GB)
- First download can take 10-30 minutes depending on internet speed
- Models are cached in `~/.cache/huggingface/` for future use
- Consider pre-downloading models on a faster connection

### Issue: ImportError: No module named 'qwen_vl_utils'

**Symptom:** Error when loading Qwen3-VL models

**Solution:**
```bash
uv pip install qwen-vl-utils
```

### Issue: Transformers version conflict

**Symptom:** `transformers version X.X.X is not compatible with Qwen3-VL`

**Solution:**
```bash
# MUST use transformers 4.57.0 or newer
uv pip install --upgrade transformers>=4.57.1
```

## Quick Start Scripts

### Daily Usage Script

Create `~/ocr_env.sh` for quick activation:

```bash
#!/bin/bash
cd ~/code/ocr-service
source .venv/bin/activate
export CUDA_VISIBLE_DEVICES=0,1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True,max_split_size_mb:96
export MALLOC_ARENA_MAX=2
echo "OCR Service environment activated"
```

Usage:
```bash
source ~/ocr_env.sh
ocr image.jpg
```

### System Service (Optional)

For production deployment, create a systemd service:

```ini
# /etc/systemd/system/ocr-api.service
[Unit]
Description=OCR Service API
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/home/your-username/code/ocr-service
Environment="CUDA_VISIBLE_DEVICES=0,1"
Environment="PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True,max_split_size_mb:96"
ExecStart=/home/your-username/code/ocr-service/.venv/bin/python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable ocr-api
sudo systemctl start ocr-api
```

## Validation Checklist

After installation, verify everything works:

- [ ] GPU detected: `nvidia-smi`
- [ ] CUDA available: `nvcc --version`
- [ ] Python 3.11+: `python --version`
- [ ] Virtual environment activated: `which python`
- [ ] Transformers 4.57.1+: `python -c "import transformers; print(transformers.__version__)"`
- [ ] Flash Attention (optional): `python -c "import flash_attn; print('OK')"`
- [ ] Environment variables set: `echo $CUDA_VISIBLE_DEVICES`
- [ ] Qwen3-VL works: `uv run python test_qwen3.py`
- [ ] DeepSeek-OCR works: `uv run python test_deepseek_ocr.py`
- [ ] CLI works: `ocr gpu && ocr models`

All checks passed? ✅ **Installation complete!**

## Next Steps

1. **Read the documentation:**
   - [README.md](../README.md) - Main documentation
   - [docs/DEEPSEEK_OCR_PATCHES.md](DEEPSEEK_OCR_PATCHES.md) - Patch details
   - [docs/API_REFERENCE.md](API_REFERENCE.md) - API documentation

2. **Try the web interface:**
   ```bash
   cd web
   npm install
   npm run dev
   ```

3. **Process your first document:**
   ```bash
   ocr pdf your-document.pdf --output result.txt
   ```

## Deployment to New Server Checklist

When deploying to a new server, follow this checklist:

### Pre-Deployment
- [ ] Server meets hardware requirements (6GB+ VRAM)
- [ ] Ubuntu 22.04+ installed
- [ ] SSH access configured
- [ ] Firewall rules configured (if using API)

### Installation
- [ ] Install system dependencies (Python, CUDA, build tools)
- [ ] Install uv package manager
- [ ] Clone repository
- [ ] Create virtual environment
- [ ] Install PyTorch with CUDA support
- [ ] Install transformers 4.57.1+
- [ ] Install all dependencies
- [ ] Install Flash Attention 2 (optional)
- [ ] Set environment variables
- [ ] Add environment variables to shell profile

### Configuration
- [ ] Create `.env` file with correct settings
- [ ] Configure GPU settings (CUDA_VISIBLE_DEVICES)
- [ ] Configure memory settings (PYTORCH_CUDA_ALLOC_CONF)
- [ ] Test GPU detection: `ocr gpu`

### DeepSeek-OCR Patches
- [ ] Make patch script executable: `chmod +x patch_deepseek_model.sh`
- [ ] Patches copied to project root
- [ ] Python helper scripts present (fix_attention_mask.py, fix_attention_return.py)

### Validation
- [ ] Run Qwen3-VL test: `uv run python test_qwen3.py` (should pass)
- [ ] Run DeepSeek-OCR test: `uv run python test_deepseek_ocr.py` (should pass)
- [ ] Test CLI: `ocr models` (should list all models)
- [ ] Test single image: `ocr image.jpg`
- [ ] Test PDF: `ocr pdf document.pdf -o output.txt`

### Production (Optional)
- [ ] Create systemd service
- [ ] Configure reverse proxy (nginx)
- [ ] Set up SSL certificates
- [ ] Configure monitoring
- [ ] Set up log rotation
- [ ] Configure backups

## Support

If you encounter issues not covered in this guide:

1. Check the [troubleshooting section](../README.md#-troubleshooting) in main README
2. Review [docs/DEEPSEEK_OCR_PATCHES.md](DEEPSEEK_OCR_PATCHES.md) for patch-related issues
3. Run validation tests to identify specific problems
4. Check logs for detailed error messages

## Summary

This installation guide covers:
- ✅ Complete system setup from scratch
- ✅ All required dependencies
- ✅ DeepSeek-OCR compatibility patches
- ✅ Environment configuration
- ✅ Troubleshooting common issues
- ✅ Validation procedures
- ✅ Deployment checklist

Follow this guide to successfully deploy the OCR service on any new server!
