#!/usr/bin/env python3
"""
Verify OCR Service installation.

This script checks:
- Python version
- Required packages and versions
- CUDA availability
- GPU information
- Model configs
"""
import sys
from pathlib import Path
import importlib.util


def check_python_version():
    """Check Python version."""
    version = sys.version_info
    if version.major == 3 and version.minor >= 11:
        print(f"✓ Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"✗ Python {version.major}.{version.minor}.{version.micro} (requires 3.11+)")
        return False


def check_package(name: str, required_version: str = None):
    """Check if a package is installed."""
    try:
        module = __import__(name)
        version = getattr(module, "__version__", "unknown")
        
        if required_version:
            if version == required_version:
                print(f"✓ {name} {version}")
                return True
            else:
                print(f"⚠ {name} {version} (expected {required_version})")
                return False
        else:
            print(f"✓ {name} {version}")
            return True
    except ImportError:
        print(f"✗ {name} not installed")
        return False


def check_cuda():
    """Check CUDA availability."""
    try:
        import torch
        if torch.cuda.is_available():
            print(f"✓ CUDA {torch.version.cuda} available")
            print(f"  GPU count: {torch.cuda.device_count()}")
            for i in range(torch.cuda.device_count()):
                name = torch.cuda.get_device_name(i)
                total_mem = torch.cuda.get_device_properties(i).total_memory / 1024**3
                print(f"    GPU {i}: {name} ({total_mem:.1f} GB)")
            return True
        else:
            print("✗ CUDA not available")
            return False
    except Exception as e:
        print(f"✗ Error checking CUDA: {e}")
        return False


def check_flash_attention():
    """Check Flash-Attention (optional but recommended)."""
    try:
        import flash_attn
        print(f"✓ Flash-Attention {flash_attn.__version__} (installed)")
        print("  → 30-40% VRAM savings enabled")
        return True
    except ImportError:
        print("⚠ Flash-Attention not installed (optional but recommended)")
        print("  → Models will use standard attention (higher VRAM usage)")
        print("  → To install: ./scripts/install_flash_attention.sh")
        print("  → See: specs/flash-attention-setup.md")
        # Return True because it's optional - don't fail the verification
        return True


def check_project_structure():
    """Check project structure."""
    required_paths = [
        "config/model_configs.yaml",
        "config/settings.py",
        "src/models/base.py",
        "src/models/qwen_vl.py",
        "src/models/deepseek_ocr.py",
        "src/models/model_manager.py",
        "src/cli/commands.py",
        ".env.example",
    ]
    
    all_exist = True
    for path in required_paths:
        file_path = Path(path)
        if file_path.exists():
            print(f"✓ {path}")
        else:
            print(f"✗ {path} missing")
            all_exist = False
    
    return all_exist


def check_environment():
    """Check environment variables."""
    import os
    
    env_vars = [
        "CUDA_VISIBLE_DEVICES",
        "PYTORCH_CUDA_ALLOC_CONF",
        "MALLOC_ARENA_MAX",
    ]
    
    all_set = True
    for var in env_vars:
        value = os.environ.get(var)
        if value:
            print(f"✓ {var}={value}")
        else:
            print(f"⚠ {var} not set")
            all_set = False
    
    return all_set


def main():
    """Run verification checks."""
    print("=" * 80)
    print("OCR Service Installation Verification")
    print("=" * 80)
    print()
    
    checks = []
    
    # Python version
    print("Checking Python version...")
    checks.append(check_python_version())
    print()
    
    # Core packages
    print("Checking core packages...")
    checks.append(check_package("torch", "2.5.1+cu124"))
    checks.append(check_package("transformers", "4.46.3"))
    checks.append(check_package("tokenizers"))
    checks.append(check_package("accelerate"))
    checks.append(check_package("safetensors"))
    print()
    
    # Flash-Attention
    print("Checking Flash-Attention...")
    checks.append(check_flash_attention())
    print()
    
    # CUDA
    print("Checking CUDA...")
    checks.append(check_cuda())
    print()
    
    # Dependencies
    print("Checking additional dependencies...")
    check_package("PIL")  # Pillow
    check_package("click")
    check_package("rich")
    check_package("fitz")  # PyMuPDF
    check_package("yaml")
    check_package("pydantic")
    print()
    
    # Project structure
    print("Checking project structure...")
    checks.append(check_project_structure())
    print()
    
    # Environment variables
    print("Checking environment variables...")
    env_ok = check_environment()
    if not env_ok:
        print("\n  To set environment variables, run:")
        print("    source scripts/quick_start.sh")
    print()
    
    # Summary
    print("=" * 80)
    if all(checks):
        print("✓ All critical checks passed!")
        print()
        print("Next steps:")
        print("  1. Run: source scripts/quick_start.sh")
        print("  2. Test: ocr --help")
        print("  3. Test: ocr gpu")
        print("  4. Try: python examples/test_models.py")
    else:
        print("✗ Some checks failed. Please review the output above.")
        print()
        print("Common fixes:")
        print("  - Run: ./scripts/setup.sh")
        print("  - For Flash-Attention: uv pip install flash-attn --no-build-isolation")
        print("  - For environment: source scripts/quick_start.sh")
    print("=" * 80)


if __name__ == "__main__":
    main()

