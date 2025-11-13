#!/bin/bash
#
# FlashAttention 2 Installation Helper Script
#
# This script automates the installation of FlashAttention 2 with proper
# prerequisite checking and fallback recommendations.
#
# Usage:
#   ./scripts/install_flash_attention.sh
#
# Exit codes:
#   0 - Installation successful
#   1 - Prerequisites not met
#   2 - Installation failed
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print functions
print_header() {
    echo -e "\n${BLUE}======================================================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}======================================================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "${BLUE}→${NC} $1"
}

# Check if virtual environment is activated
check_venv() {
    if [[ -z "$VIRTUAL_ENV" ]]; then
        print_error "Virtual environment not activated"
        print_info "Please activate the virtual environment first:"
        echo "  source .venv/bin/activate"
        exit 1
    fi
    print_success "Virtual environment: $VIRTUAL_ENV"
}

# Run prerequisite checks
check_prerequisites() {
    print_header "Checking Prerequisites"

    # Check if verification script exists
    if [[ ! -f "scripts/verify_flash_attention.py" ]]; then
        print_error "Verification script not found: scripts/verify_flash_attention.py"
        exit 1
    fi

    # Run prerequisite checks
    if python scripts/verify_flash_attention.py --check-prereqs; then
        print_success "All prerequisites satisfied"
        return 0
    else
        print_error "Prerequisites not met"
        echo
        print_info "Please install missing components before proceeding."
        print_info "See specs/flash-attention-setup.md for detailed instructions."
        exit 1
    fi
}

# Install flash-attn
install_flash_attn() {
    print_header "Installing FlashAttention 2"

    print_info "This may take 5-10 minutes..."
    print_info "The package will be compiled from source"
    echo

    # Determine pip command (prefer uv)
    if command -v uv &> /dev/null; then
        PIP_CMD="uv pip"
        print_info "Using uv pip for installation"
    else
        PIP_CMD="pip"
        print_info "Using pip for installation (uv not found)"
    fi

    # Install flash-attn
    echo "Running: $PIP_CMD install flash-attn --no-build-isolation"
    echo

    if $PIP_CMD install flash-attn --no-build-isolation; then
        print_success "flash-attn package installed successfully"
        return 0
    else
        print_error "Installation failed"
        return 1
    fi
}

# Verify installation
verify_installation() {
    print_header "Verifying Installation"

    if python scripts/verify_flash_attention.py; then
        return 0
    else
        return 1
    fi
}

# Provide fallback instructions
print_fallback_instructions() {
    print_header "Fallback: Disable FlashAttention 2"

    echo "If installation cannot be completed, you can disable FlashAttention 2"
    echo "and use standard attention mechanisms instead."
    echo
    echo "Edit config/model_configs.yaml and comment out the following lines:"
    echo
    echo "For Qwen3-VL-8B (line 17):"
    echo "  # _attn_implementation: \"flash_attention_2\""
    echo
    echo "For DeepSeek-OCR (line 80):"
    echo "  # _attn_implementation: \"flash_attention_2\""
    echo
    echo "Note: This will increase VRAM usage by ~3-4 GB per model"
    echo "See specs/flash-attention-setup.md for detailed information"
}

# Main installation flow
main() {
    print_header "FlashAttention 2 Installation"

    echo "This script will install FlashAttention 2 for memory-efficient inference."
    echo "Installation requires CUDA toolkit and may take 5-10 minutes."
    echo
    read -p "Continue with installation? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 0
    fi

    # Step 1: Check virtual environment
    check_venv

    # Step 2: Check prerequisites
    check_prerequisites

    # Step 3: Install flash-attn
    if ! install_flash_attn; then
        print_error "Installation failed"
        echo
        print_info "Troubleshooting steps:"
        echo "  1. Check CUDA toolkit is in PATH:"
        echo "     export PATH=/usr/local/cuda/bin:\$PATH"
        echo "  2. Try with verbose output:"
        echo "     uv pip install flash-attn --no-build-isolation --verbose"
        echo "  3. Check installation logs for specific errors"
        echo "  4. See specs/flash-attention-setup.md for detailed troubleshooting"
        echo
        print_fallback_instructions
        exit 2
    fi

    # Step 4: Verify installation
    if ! verify_installation; then
        print_warning "Installation completed but verification failed"
        echo
        print_info "Possible issues:"
        echo "  • CUDA libraries not in LD_LIBRARY_PATH"
        echo "  • Installation corrupted"
        echo
        print_info "Try running diagnostics:"
        echo "  python scripts/verify_flash_attention.py --diagnose"
        echo
        print_fallback_instructions
        exit 2
    fi

    # Success!
    print_header "Installation Complete"

    print_success "FlashAttention 2 is now installed and functional!"
    echo
    echo "Benefits:"
    echo "  • 30-40% memory savings during inference"
    echo "  • 20-30% faster processing speeds"
    echo "  • Better support for high-resolution documents"
    echo
    echo "Next steps:"
    echo "  1. Restart the API server:"
    echo "     ./scripts/start_api.sh"
    echo "  2. Process a test document to verify performance"
    echo
    echo "For configuration details, see: config/model_configs.yaml"
    echo "For troubleshooting, see: specs/flash-attention-setup.md"

    exit 0
}

# Run main function
main "$@"
