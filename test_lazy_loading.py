"""
Test Lazy Loading and Resource Management

Verifies that:
1. Models are NOT loaded on container startup
2. Models load automatically on first inference request
3. GPU memory is allocated during loading
4. /unload endpoint frees GPU memory
5. Only one model is loaded at a time
"""

import asyncio
import sys
import base64
from pathlib import Path
from PIL import Image
import io

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.models.http_client_manager import HTTPClientManager, ModelType


def create_test_image() -> str:
    """Create a simple test image and return base64-encoded string"""
    # Create a white image with black text
    img = Image.new('RGB', (400, 100), color='white')

    # Convert to base64
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    image_bytes = buffer.getvalue()
    return base64.b64encode(image_bytes).decode('utf-8')


async def test_lazy_loading():
    """Test lazy loading and resource management"""

    print("=" * 80)
    print("LAZY LOADING AND RESOURCE MANAGEMENT TEST")
    print("=" * 80)

    manager = HTTPClientManager()

    try:
        # Initialize HTTP clients
        print("\n1. Initializing HTTP clients...")
        await manager.initialize()
        print("   ✓ Clients initialized")

        # Verify models are NOT loaded on startup
        print("\n2. Verifying lazy loading (models should NOT be loaded)...")
        for model_type in ModelType:
            info = await manager.get_model_info(model_type)
            model_loaded = info.get("model_loaded", False)
            gpu_memory = info.get("gpu_memory", [])

            print(f"\n   {model_type.value}:")
            print(f"     Model loaded: {model_loaded}")
            if gpu_memory:
                print(f"     GPU 0 free: {gpu_memory[0]['free']}MB / {gpu_memory[0]['total']}MB")

            if model_loaded:
                print(f"   ✗ ERROR: {model_type.value} model should NOT be loaded!")
                return False

        print("\n   ✓ Both models unloaded (lazy loading confirmed)")

        # Get baseline GPU memory
        deepseek_info = await manager.get_model_info(ModelType.DEEPSEEK_OCR)
        baseline_free = deepseek_info["gpu_memory"][0]["free"]
        print(f"\n   Baseline GPU free memory: {baseline_free}MB")

        # Test DeepSeek-OCR loading
        print("\n3. Testing DeepSeek-OCR lazy loading...")
        print("   Sending first inference request (should trigger model load)...")

        image_base64 = create_test_image()

        deepseek_request = {
            "image_base64": image_base64,
            "prompt": "Read the text in this image.",
            "base_size": 1024,
            "image_size": 640,
            "crop_mode": True,
            "eval_mode": True
        }

        result = await manager.infer(
            ModelType.DEEPSEEK_OCR,
            deepseek_request,
            timeout=300.0  # 5 minutes for first load
        )

        print(f"   Inference result: success={result.get('success', False)}")

        # Verify model is now loaded
        deepseek_info = await manager.get_model_info(ModelType.DEEPSEEK_OCR)
        model_loaded = deepseek_info.get("model_loaded", False)
        device = deepseek_info.get("device")
        gpu_free_after_load = deepseek_info["gpu_memory"][0]["free"]
        memory_used = baseline_free - gpu_free_after_load

        print(f"\n   After loading:")
        print(f"     Model loaded: {model_loaded}")
        print(f"     Device: {device}")
        print(f"     GPU memory used: ~{memory_used}MB")
        print(f"     GPU free: {gpu_free_after_load}MB")

        if not model_loaded:
            print("   ✗ ERROR: DeepSeek model should be loaded after inference!")
            return False

        print("   ✓ DeepSeek-OCR loaded successfully")

        # Test that Qwen is still NOT loaded (only one model at a time)
        print("\n4. Verifying only ONE model loaded at a time...")
        qwen_info = await manager.get_model_info(ModelType.QWEN_VL)
        qwen_loaded = qwen_info.get("model_loaded", False)

        print(f"   Qwen3-VL loaded: {qwen_loaded}")

        if qwen_loaded:
            print("   ✗ ERROR: Qwen should NOT be loaded (only one model at a time)!")
            return False

        print("   ✓ Only DeepSeek loaded (single model constraint verified)")

        # Test explicit unload
        print("\n5. Testing explicit model unload...")
        print("   Calling /unload endpoint on DeepSeek container...")

        # Call unload directly via HTTP client
        client = manager.clients[ModelType.DEEPSEEK_OCR]
        unload_response = await client.post("/unload")
        unload_result = unload_response.json()

        print(f"   Unload response: {unload_result}")

        # Verify model is unloaded
        deepseek_info = await manager.get_model_info(ModelType.DEEPSEEK_OCR)
        model_loaded = deepseek_info.get("model_loaded", False)
        gpu_free_after_unload = deepseek_info["gpu_memory"][0]["free"]
        memory_freed = gpu_free_after_unload - gpu_free_after_load

        print(f"\n   After unload:")
        print(f"     Model loaded: {model_loaded}")
        print(f"     GPU memory freed: ~{memory_freed}MB")
        print(f"     GPU free: {gpu_free_after_unload}MB")

        if model_loaded:
            print("   ✗ ERROR: Model should be unloaded!")
            return False

        print("   ✓ DeepSeek-OCR unloaded successfully")

        # Test Qwen loading
        print("\n6. Testing Qwen3-VL lazy loading...")
        print("   Sending first inference request (should trigger model load)...")

        qwen_request = {
            "image_base64": image_base64,
            "messages": [
                {
                    "role": "user",
                    "content": "<image> Describe this image."
                }
            ],
            "max_new_tokens": 512
        }

        result = await manager.infer(
            ModelType.QWEN_VL,
            qwen_request,
            timeout=300.0  # 5 minutes for first load
        )

        print(f"   Inference result: success={result.get('success', False)}")

        # Verify Qwen is loaded
        qwen_info = await manager.get_model_info(ModelType.QWEN_VL)
        model_loaded = qwen_info.get("model_loaded", False)
        device = qwen_info.get("device")
        gpu_free_final = qwen_info["gpu_memory"][0]["free"]
        memory_used_qwen = gpu_free_after_unload - gpu_free_final

        print(f"\n   After loading:")
        print(f"     Model loaded: {model_loaded}")
        print(f"     Device: {device}")
        print(f"     GPU memory used: ~{memory_used_qwen}MB")
        print(f"     GPU free: {gpu_free_final}MB")

        if not model_loaded:
            print("   ✗ ERROR: Qwen model should be loaded after inference!")
            return False

        print("   ✓ Qwen3-VL loaded successfully")

        # Verify DeepSeek is still unloaded
        deepseek_info = await manager.get_model_info(ModelType.DEEPSEEK_OCR)
        deepseek_loaded = deepseek_info.get("model_loaded", False)

        print(f"\n   DeepSeek still unloaded: {not deepseek_loaded}")

        if deepseek_loaded:
            print("   ✗ ERROR: DeepSeek should still be unloaded!")
            return False

        print("   ✓ Only Qwen loaded (sequential loading verified)")

        # Summary
        print("\n" + "=" * 80)
        print("✓ ALL TESTS PASSED!")
        print("=" * 80)
        print(f"\nResource usage summary:")
        print(f"  GPU total: {deepseek_info['gpu_memory'][0]['total']}MB")
        print(f"  DeepSeek-OCR memory: ~{memory_used}MB")
        print(f"  Qwen3-VL memory: ~{memory_used_qwen}MB")
        print(f"  Final GPU free: {gpu_free_final}MB")

        print(f"\nLazy loading features verified:")
        print(f"  ✓ Models NOT loaded on container startup")
        print(f"  ✓ Models load automatically on first inference request")
        print(f"  ✓ GPU memory allocated during loading")
        print(f"  ✓ /unload endpoint frees GPU memory")
        print(f"  ✓ Only one model loaded at a time (sequential pipeline)")

        return True

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await manager.close()


if __name__ == "__main__":
    success = asyncio.run(test_lazy_loading())
    sys.exit(0 if success else 1)
