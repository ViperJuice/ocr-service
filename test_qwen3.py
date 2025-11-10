#!/usr/bin/env python3
"""
Test Qwen3-VL model with transformers 4.57.1 to ensure compatibility
"""

import sys
import torch
from pathlib import Path
from PIL import Image

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.models.qwen_vl import QwenVLModel

def test_qwen3_vl():
    """Test Qwen3-VL with a sample image."""

    print("=" * 80)
    print("Testing Qwen3-VL with transformers 4.57.1")
    print("=" * 80)

    # Initialize model
    print("\n1. Loading Qwen3-VL model...")

    # Use Qwen3-VL-4B for testing (faster, less memory)
    model = QwenVLModel(
        model_id="Qwen/Qwen3-VL-4B-Instruct",
        config={
            "torch_dtype": "float16",
            "device_map": "cuda:0",
            "low_cpu_mem_usage": True,
            "config": {
                "_attn_implementation": "flash_attention_2"
            },
            "generation_config": {
                "max_new_tokens": 200,
                "temperature": 0.1,
                "top_p": 0.9,
                "do_sample": False,
            }
        },
    )
    model.load()
    print("   ✓ Model loaded successfully")

    # Load test image
    test_image_path = Path("tests/api/fixtures/sample.pdf")
    if not test_image_path.exists():
        print(f"   ✗ Test file not found: {test_image_path}")
        return False

    # Convert first page to image
    print("\n2. Loading test image from PDF...")
    import fitz  # PyMuPDF

    doc = fitz.open(test_image_path)
    page = doc[0]

    # Render at lower resolution for quick test (72 DPI)
    pix = page.get_pixmap(dpi=72)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    print(f"   ✓ Image loaded: {img.size[0]}x{img.size[1]} pixels")

    # Test with OCR extraction
    print("\n3. Running inference...")

    result = model.process_image(
        image=img,
        prompt_type="ocr",
        max_new_tokens=200,
    )

    print(f"\n   ✓ Inference completed successfully!")
    print(f"\n4. Results:")
    print(f"   Model: {result.model_name}")
    print(f"   Processing time: {result.processing_time:.2f}s")
    print(f"   Extracted text (first 500 chars): {result.text[:500]}...")
    print(f"   Total text length: {len(result.text)} characters")

    # Clean up
    doc.close()

    print("\n" + "=" * 80)
    print("✓ SUCCESS! Qwen3-VL is fully working with transformers 4.57.1!")
    print("=" * 80)

    return True

if __name__ == "__main__":
    try:
        success = test_qwen3_vl()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
