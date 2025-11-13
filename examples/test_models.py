#!/usr/bin/env python3
"""
Test all three models to verify they load correctly.

This script tests:
- Qwen3-VL-2B
- Qwen3-VL-8B
- DeepSeek-OCR

Based on the test_large_models.py pattern from DeepSeek-OCR repo.
"""
from pathlib import Path
from PIL import Image
import sys
import time

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import get_settings
from src.models import ModelManager
from src.utils import get_gpu_info, clear_gpu_memory


def test_model(manager: ModelManager, model_name: str, test_image: Image.Image) -> dict:
    """
    Test a single model.
    
    Returns:
        Dict with test results
    """
    print(f"\n{'=' * 80}")
    print(f"Testing: {model_name}")
    print(f"{'=' * 80}")
    
    result = {
        "model_name": model_name,
        "success": False,
        "load_time": None,
        "inference_time": None,
        "vram_used": None,
        "error": None,
    }
    
    try:
        # Clear memory before test
        clear_gpu_memory()
        
        # Load model
        print("Loading model...")
        start = time.time()
        model = manager.load_model(model_name)
        load_time = time.time() - start
        result["load_time"] = load_time
        
        print(f"✓ Model loaded in {load_time:.1f}s")
        
        # Check memory usage
        memory = model.get_memory_usage()
        total_vram = sum(memory.values())
        result["vram_used"] = total_vram
        
        print(f"  Memory usage: {memory}")
        print(f"  Total VRAM: {total_vram:.2f} GB")
        
        # Run inference
        print("\nRunning inference...")
        start = time.time()
        ocr_result = model.process_image(test_image)
        inference_time = time.time() - start
        result["inference_time"] = inference_time
        
        print(f"✓ Inference completed in {inference_time:.2f}s")
        print(f"  Text length: {len(ocr_result.text)} characters")
        print(f"  Text preview: {ocr_result.text[:100]}...")
        
        result["success"] = True
        
        # Unload model
        manager.unload_model(model_name)
        clear_gpu_memory()
        
    except Exception as e:
        result["error"] = str(e)
        print(f"\n✗ FAILED: {e}")
        
        # Try to clean up
        try:
            manager.unload_model(model_name)
            clear_gpu_memory()
        except:
            pass
    
    return result


def main():
    """Run model tests."""
    print("=" * 80)
    print("OCR Service - Model Verification")
    print("=" * 80)
    print()
    
    # System info
    print("System Information:")
    gpu_info = get_gpu_info()
    if gpu_info["cuda_available"]:
        print(f"  CUDA Version: {gpu_info['cuda_version']}")
        print(f"  GPU Count: {gpu_info['device_count']}")
        print(f"  Total VRAM: {gpu_info['total_memory_gb']:.2f} GB")
        for device in gpu_info["devices"]:
            print(f"    GPU {device['id']}: {device['name']} ({device['total_memory_gb']:.1f} GB)")
    else:
        print("  CUDA: Not available")
    print()
    
    # Load settings
    settings = get_settings()
    model_configs = settings.load_model_configs()
    
    # Initialize manager
    manager = ModelManager(model_configs["models"])
    
    # Create test image
    print("Creating test image...")
    from PIL import ImageDraw
    test_image = Image.new('RGB', (800, 600), color='white')
    draw = ImageDraw.Draw(test_image)
    draw.text(
        (50, 50),
        "OCR Test Document\n\n"
        "This is a test image for model verification.\n\n"
        "Features to test:\n"
        "- Text extraction\n"
        "- Layout preservation\n"
        "- Speed measurement",
        fill='black'
    )
    print("✓ Test image created")
    print()
    
    # Test models in order (smallest to largest)
    models_to_test = [
        "qwen2-vl-2b",    # 3GB - smallest
        "deepseek-ocr",   # 6GB - medium
        "qwen2-vl-7b",    # 13GB - largest
    ]
    
    results = []
    for model_name in models_to_test:
        result = test_model(manager, model_name, test_image)
        results.append(result)
        time.sleep(2)  # Brief pause between tests
    
    # Print summary
    print("\n" + "=" * 80)
    print("Test Summary")
    print("=" * 80)
    print(f"\n{'Model':<20} {'Status':<10} {'Load Time':<12} {'Inference':<12} {'VRAM Used':<12}")
    print("-" * 80)
    
    for r in results:
        status = "✓ PASS" if r["success"] else "✗ FAIL"
        load_time = f"{r['load_time']:.1f}s" if r['load_time'] else "N/A"
        inference = f"{r['inference_time']:.2f}s" if r['inference_time'] else "N/A"
        vram = f"{r['vram_used']:.2f} GB" if r['vram_used'] else "N/A"
        
        print(f"{r['model_name']:<20} {status:<10} {load_time:<12} {inference:<12} {vram:<12}")
        
        if not r['success'] and r['error']:
            print(f"  Error: {r['error'][:70]}...")
    
    print()
    
    # Recommendations
    successful = [r for r in results if r["success"]]
    if successful:
        print("✓ All models loaded successfully!")
        print()
        print("Recommendations:")
        
        # Fastest
        fastest = min(successful, key=lambda x: x["inference_time"])
        print(f"  • Fastest: {fastest['model_name']} ({fastest['inference_time']:.2f}s per image)")
        
        # Most memory efficient
        smallest = min(successful, key=lambda x: x["vram_used"])
        print(f"  • Most efficient: {smallest['model_name']} ({smallest['vram_used']:.2f} GB VRAM)")
        
        # Best quality (assume 7B is best)
        print(f"  • Best quality: qwen2-vl-7b (highest parameter count)")
        
    else:
        print("✗ Some models failed to load. Check errors above.")
    
    print()
    print("=" * 80)


if __name__ == "__main__":
    main()

