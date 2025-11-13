#!/usr/bin/env python3
"""
FlashAttention 2 Verification Script

This script checks prerequisites, installation status, and functionality of FlashAttention 2.
It provides detailed diagnostics and actionable recommendations.

Usage:
    python scripts/verify_flash_attention.py                 # Full verification
    python scripts/verify_flash_attention.py --check-prereqs # Only check prerequisites
    python scripts/verify_flash_attention.py --diagnose      # Detailed diagnostics

Exit codes:
    0 - FlashAttention 2 is fully operational
    1 - FlashAttention 2 not installed
    2 - Prerequisites not met (incompatible hardware/software)
    3 - Installation corrupted or non-functional
"""

import sys
import subprocess
import argparse
from pathlib import Path


def print_header(title: str):
    """Print a formatted section header."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def print_check(passed: bool, message: str, details: str = ""):
    """Print a check result with consistent formatting."""
    symbol = "✓" if passed else "✗"
    color = "\033[92m" if passed else "\033[91m"  # Green or Red
    reset = "\033[0m"
    print(f"{color}{symbol}{reset} {message}")
    if details:
        print(f"  → {details}")


def check_cuda_toolkit() -> tuple[bool, str]:
    """Check if CUDA toolkit is installed and get version."""
    try:
        result = subprocess.run(
            ["nvcc", "--version"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            # Extract version from output
            for line in result.stdout.split('\n'):
                if 'release' in line.lower():
                    version = line.split('release')[1].split(',')[0].strip()
                    return True, version
        return False, "nvcc not found in PATH"
    except FileNotFoundError:
        return False, "CUDA toolkit not installed"


def check_gpu_compute_capability() -> tuple[bool, str]:
    """Check GPU compute capability using nvidia-smi."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,compute_cap", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split('\n')
            gpu_info = []
            all_compatible = True

            for line in lines:
                parts = line.split(',')
                if len(parts) >= 2:
                    gpu_name = parts[0].strip()
                    compute_cap = parts[1].strip()

                    try:
                        cap_float = float(compute_cap)
                        compatible = cap_float >= 7.5
                        gpu_info.append(f"{gpu_name} (CC {compute_cap})")
                        if not compatible:
                            all_compatible = False
                    except ValueError:
                        all_compatible = False

            if all_compatible:
                return True, ", ".join(gpu_info)
            else:
                return False, f"Insufficient compute capability: {', '.join(gpu_info)} (need ≥7.5)"

        return False, "No NVIDIA GPU detected"
    except FileNotFoundError:
        return False, "nvidia-smi not found"


def check_python_dev_headers() -> tuple[bool, str]:
    """Check if Python development headers are installed."""
    try:
        import distutils.sysconfig
        import os

        include_path = distutils.sysconfig.get_python_inc()
        python_h = Path(include_path) / "Python.h"

        if python_h.exists():
            return True, str(include_path)
        else:
            return False, f"Python.h not found at {include_path}"
    except Exception as e:
        return False, str(e)


def check_cpp_compiler() -> tuple[bool, str]:
    """Check if C++ compiler (g++) is available and get version."""
    try:
        result = subprocess.run(
            ["g++", "--version"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            # Extract version number
            parts = version_line.split()
            for part in parts:
                if part[0].isdigit():
                    return True, part
            return True, "installed"
        return False, "g++ not found"
    except FileNotFoundError:
        return False, "g++ not installed"


def check_pytorch_cuda() -> tuple[bool, str]:
    """Check if PyTorch is installed with CUDA support."""
    try:
        import torch

        if not torch.cuda.is_available():
            return False, f"PyTorch {torch.__version__} installed but CUDA not available"

        cuda_version = torch.version.cuda
        return True, f"PyTorch {torch.__version__} with CUDA {cuda_version}"
    except ImportError:
        return False, "PyTorch not installed"


def check_flash_attn_installed() -> tuple[bool, str]:
    """Check if flash-attn package is installed."""
    try:
        import flash_attn
        return True, flash_attn.__version__
    except ImportError:
        return False, "Package not installed"


def check_transformers_compatibility() -> tuple[bool, str]:
    """Check if transformers version is compatible with flash-attn."""
    try:
        import transformers

        # transformers >= 4.34.0 is needed for FlashAttention 2
        version = transformers.__version__
        major, minor = map(int, version.split('.')[:2])

        if major > 4 or (major == 4 and minor >= 34):
            return True, version
        else:
            return False, f"{version} (need ≥4.34.0)"
    except ImportError:
        return False, "transformers not installed"


def check_flash_attn_functional() -> tuple[bool, str]:
    """Run a minimal functional test of FlashAttention."""
    try:
        import torch
        from flash_attn import flash_attn_func

        # Create minimal test tensors
        batch_size, seqlen, num_heads, head_dim = 1, 128, 4, 64
        device = 'cuda:0'

        q = torch.randn(batch_size, seqlen, num_heads, head_dim, device=device, dtype=torch.float16)
        k = torch.randn(batch_size, seqlen, num_heads, head_dim, device=device, dtype=torch.float16)
        v = torch.randn(batch_size, seqlen, num_heads, head_dim, device=device, dtype=torch.float16)

        # Run FlashAttention
        output = flash_attn_func(q, k, v)

        if output.shape == q.shape:
            return True, "Functional test passed"
        else:
            return False, f"Output shape mismatch: {output.shape} != {q.shape}"

    except Exception as e:
        return False, f"Functional test failed: {str(e)}"


def run_prerequisite_checks() -> bool:
    """Run all prerequisite checks. Returns True if all pass."""
    print_header("Checking Prerequisites")

    all_passed = True

    # Check CUDA toolkit
    passed, details = check_cuda_toolkit()
    print_check(passed, "CUDA toolkit", details)
    all_passed &= passed

    # Check GPU compute capability
    passed, details = check_gpu_compute_capability()
    print_check(passed, "GPU compute capability", details)
    all_passed &= passed

    # Check Python dev headers
    passed, details = check_python_dev_headers()
    print_check(passed, "Python development headers", details)
    all_passed &= passed

    # Check C++ compiler
    passed, details = check_cpp_compiler()
    print_check(passed, "C++ compiler (g++)", details)
    all_passed &= passed

    # Check PyTorch with CUDA
    passed, details = check_pytorch_cuda()
    print_check(passed, "PyTorch CUDA support", details)
    all_passed &= passed

    return all_passed


def run_installation_checks() -> bool:
    """Run flash-attn installation checks. Returns True if installed and functional."""
    print_header("Checking FlashAttention 2 Installation")

    all_passed = True

    # Check if flash-attn is installed
    passed, details = check_flash_attn_installed()
    print_check(passed, "flash-attn package", details)
    all_passed &= passed

    if not passed:
        print("\n💡 Installation command:")
        print("   uv pip install flash-attn --no-build-isolation")
        return False

    # Check transformers compatibility
    passed, details = check_transformers_compatibility()
    print_check(passed, "transformers compatibility", details)
    all_passed &= passed

    # Check if CUDA kernels are available
    try:
        import flash_attn.flash_attn_interface
        print_check(True, "CUDA kernels available", "flash_attn_interface module loaded")
    except Exception as e:
        print_check(False, "CUDA kernels", str(e))
        all_passed = False

    return all_passed


def run_functional_test() -> bool:
    """Run functional test of FlashAttention. Returns True if test passes."""
    print_header("Running Functional Test")

    passed, details = check_flash_attn_functional()
    print_check(passed, "FlashAttention 2 functional test", details)

    return passed


def run_diagnostics():
    """Run detailed diagnostics for troubleshooting."""
    print_header("Detailed Diagnostics")

    # System info
    print("System Information:")
    try:
        import platform
        print(f"  OS: {platform.system()} {platform.release()}")
        print(f"  Python: {platform.python_version()}")
    except:
        pass

    # CUDA environment variables
    print("\nCUDA Environment:")
    import os
    cuda_vars = ['CUDA_HOME', 'CUDA_PATH', 'PATH', 'LD_LIBRARY_PATH']
    for var in cuda_vars:
        value = os.environ.get(var, '<not set>')
        if len(value) > 100:
            value = value[:100] + "..."
        print(f"  {var}: {value}")

    # PyTorch CUDA details
    print("\nPyTorch CUDA Details:")
    try:
        import torch
        print(f"  torch.cuda.is_available(): {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"  torch.version.cuda: {torch.version.cuda}")
            print(f"  torch.cuda.device_count(): {torch.cuda.device_count()}")
            for i in range(torch.cuda.device_count()):
                print(f"  GPU {i}: {torch.cuda.get_device_name(i)}")
    except Exception as e:
        print(f"  Error: {e}")

    # Flash-attn import details
    print("\nFlash-attn Import Details:")
    try:
        import flash_attn
        print(f"  Version: {flash_attn.__version__}")
        print(f"  Location: {flash_attn.__file__}")

        # Try importing key modules
        modules = [
            'flash_attn.flash_attn_interface',
            'flash_attn.flash_attn_triton',
        ]
        for module in modules:
            try:
                __import__(module)
                print(f"  ✓ {module}")
            except Exception as e:
                print(f"  ✗ {module}: {e}")
    except Exception as e:
        print(f"  Cannot import flash_attn: {e}")

    print("\n" + "="*70)


def main():
    parser = argparse.ArgumentParser(
        description="Verify FlashAttention 2 installation and prerequisites",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit codes:
  0 - FlashAttention 2 is fully operational
  1 - FlashAttention 2 not installed
  2 - Prerequisites not met
  3 - Installation corrupted or non-functional

Examples:
  python scripts/verify_flash_attention.py                 # Full verification
  python scripts/verify_flash_attention.py --check-prereqs # Only prerequisites
  python scripts/verify_flash_attention.py --diagnose      # Detailed diagnostics
        """
    )

    parser.add_argument(
        '--check-prereqs',
        action='store_true',
        help='Only check prerequisites (CUDA, compiler, etc.)'
    )

    parser.add_argument(
        '--diagnose',
        action='store_true',
        help='Run detailed diagnostics for troubleshooting'
    )

    args = parser.parse_args()

    # Run diagnostics mode
    if args.diagnose:
        run_prerequisite_checks()
        run_installation_checks()
        run_diagnostics()
        return 0

    # Run prerequisite checks only
    if args.check_prereqs:
        prereqs_passed = run_prerequisite_checks()

        if prereqs_passed:
            print("\n✅ All prerequisites satisfied. Ready to install flash-attn.")
            print("\nInstallation command:")
            print("  uv pip install flash-attn --no-build-isolation")
            return 0
        else:
            print("\n❌ Prerequisites not met. Please install missing components.")
            print("\nSee specs/flash-attention-setup.md for detailed instructions.")
            return 2

    # Full verification (default)
    prereqs_passed = run_prerequisite_checks()

    if not prereqs_passed:
        print("\n❌ Prerequisites not met. Cannot proceed with installation check.")
        print("\nSee specs/flash-attention-setup.md for detailed instructions.")
        return 2

    installation_passed = run_installation_checks()

    if not installation_passed:
        print("\n❌ FlashAttention 2 is not installed.")
        print("\nInstallation command:")
        print("  uv pip install flash-attn --no-build-isolation")
        print("\nFor detailed instructions, see: specs/flash-attention-setup.md")
        return 1

    functional_passed = run_functional_test()

    if not functional_passed:
        print("\n⚠️  FlashAttention 2 is installed but not functional.")
        print("\nTroubleshooting:")
        print("  1. Run with --diagnose flag for detailed diagnostics")
        print("  2. Try reinstalling: uv pip uninstall flash-attn && uv pip install flash-attn --no-build-isolation")
        print("  3. See specs/flash-attention-setup.md for troubleshooting guide")
        return 3

    print("\n" + "="*70)
    print("  ✅ FlashAttention 2 is fully operational!")
    print("="*70)
    print("\nYour models can now use FlashAttention 2 for:")
    print("  • 30-40% memory savings during inference")
    print("  • 20-30% faster processing speeds")
    print("  • Better support for high-resolution documents")
    print("\nModels configured with FlashAttention 2:")
    print("  • Qwen3-VL-8B")
    print("  • DeepSeek-OCR")
    print("\nFor configuration details, see: config/model_configs.yaml")

    return 0


if __name__ == "__main__":
    sys.exit(main())
