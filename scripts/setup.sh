#!/bin/bash
# Setup script for OCR Service
# For Ubuntu WSL2 with dual RTX 4090s

set -e  # Exit on error

echo "================================================================"
echo "OCR Service Setup"
echo "================================================================"
echo ""

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ]; then
    echo "Error: pyproject.toml not found. Please run this script from the project root."
    exit 1
fi

# Check for UV
if ! command -v uv &> /dev/null; then
    echo "UV not found. Installing UV..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

echo "✓ UV is available"
echo ""

# Check CUDA
if ! command -v nvcc &> /dev/null; then
    echo "Warning: nvcc not found. Make sure CUDA toolkit is installed."
else
    echo "✓ CUDA toolkit found: $(nvcc --version | grep release | awk '{print $5}' | sed 's/,//')"
fi
echo ""

# Create virtual environment
echo "Creating Python 3.11 virtual environment..."
uv venv --python 3.11
echo "✓ Virtual environment created"
echo ""

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate
echo "✓ Virtual environment activated"
echo ""

# Install PyTorch with CUDA support
echo "Installing PyTorch 2.5.1 with CUDA 12.4..."
uv pip install torch==2.5.1 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
echo "✓ PyTorch installed"
echo ""

# Install Transformers (CRITICAL VERSION!)
echo "Installing Transformers 4.46.3 (CRITICAL VERSION)..."
uv pip install transformers==4.46.3 tokenizers==0.20.3 accelerate safetensors
echo "✓ Transformers installed"
echo ""

# Install core dependencies
echo "Installing core dependencies..."
uv pip install -e .
echo "✓ Core dependencies installed"
echo ""

# Install build tools for Flash-Attention
echo "Installing build tools..."
uv pip install setuptools wheel ninja
echo "✓ Build tools installed"
echo ""

# Build Flash-Attention from source
echo "Building Flash-Attention from source..."
echo "This may take 5-10 minutes..."
uv pip install flash-attn --no-build-isolation
echo "✓ Flash-Attention installed"
echo ""

# Create necessary directories
echo "Creating project directories..."
mkdir -p data/{input,output,cache}
mkdir -p logs
echo "✓ Directories created"
echo ""

# Copy .env.example to .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env file..."
    cp .env.example .env
    echo "✓ .env file created (please review and customize)"
else
    echo "✓ .env file already exists"
fi
echo ""

# Set environment variables
echo "Setting up environment variables..."
export CUDA_VISIBLE_DEVICES=0,1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True,max_split_size_mb:96
export MALLOC_ARENA_MAX=2
export TOKENIZERS_PARALLELISM=false
echo "✓ Environment variables set"
echo ""

# Verify installation
echo "Verifying installation..."
python -c "import torch; print(f'PyTorch: {torch.__version__}')"
python -c "import transformers; print(f'Transformers: {transformers.__version__}')"
python -c "import flash_attn; print(f'Flash-Attention: {flash_attn.__version__}')" || echo "Warning: Flash-Attention import failed"
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
python -c "import torch; print(f'GPU count: {torch.cuda.device_count()}')" 
echo ""

echo "================================================================"
echo "Setup Complete!"
echo "================================================================"
echo ""
echo "Next steps:"
echo "  1. Review and customize .env file"
echo "  2. Activate the environment: source .venv/bin/activate"
echo "  3. Test the CLI: ocr --help"
echo "  4. Try a test image: ocr data/input/sample.jpg"
echo ""
echo "Environment variables (add to your shell profile):"
echo "  export CUDA_VISIBLE_DEVICES=0,1"
echo "  export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True,max_split_size_mb:96"
echo "  export MALLOC_ARENA_MAX=2"
echo ""

