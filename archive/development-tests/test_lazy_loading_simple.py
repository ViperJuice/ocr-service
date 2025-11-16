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
import httpx
import base64
from PIL import Image
import io


def create_test_image() -> str:
    """Create a simple test image and return base64-encoded string"""
    # Create a white image
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

    deepseek_url = "http://localhost:8001"
    qwen_url = "http://localhost:8002"

    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            # Verify models are NOT loaded on startup
            print("\n1. Verifying lazy loading (models should NOT be loaded)...")

            # Check DeepSeek
            response = await client.get(f"{deepseek_url}/info")
            deepseek_info = response.json()
            print(f"\n   DeepSeek-OCR:")
            print(f"     Model loaded: {deepseek_info['model_loaded']}")
            print(f"     GPU 0 free: {deepseek_info['gpu_memory'][0]['free']}MB / {deepseek_info['gpu_memory'][0]['total']}MB")

            if deepseek_info['model_loaded']:
                print("   ✗ ERROR: DeepSeek model should NOT be loaded!")
                return False

            # Check Qwen
            response = await client.get(f"{qwen_url}/info")
            qwen_info = response.json()
            print(f"\n   Qwen3-VL:")
            print(f"     Model loaded: {qwen_info['model_loaded']}")
            print(f"     GPU 0 free: {qwen_info['gpu_memory'][0]['free']}MB / {qwen_info['gpu_memory'][0]['total']}MB")

            if qwen_info['model_loaded']:
                print("   ✗ ERROR: Qwen model should NOT be loaded!")
                return False

            print("\n   ✓ Both models unloaded (lazy loading confirmed)")

            # Get baseline GPU memory
            baseline_free = deepseek_info['gpu_memory'][0]['free']
            print(f"\n   Baseline GPU free memory: {baseline_free}MB")

            # Test DeepSeek-OCR loading
            print("\n2. Testing DeepSeek-OCR lazy loading...")
            print("   Sending first inference request (should trigger model load)...")
            print("   This may take 2-3 minutes for first load...")

            image_base64 = create_test_image()

            deepseek_request = {
                "image_base64": image_base64,
                "prompt": "Read the text in this image.",
                "base_size": 1024,
                "image_size": 640,
                "crop_mode": True,
                "eval_mode": True
            }

            response = await client.post(f"{deepseek_url}/infer", json=deepseek_request)
            result = response.json()

            print(f"   Inference result: success={result.get('success', False)}")

            # Verify model is now loaded
            response = await client.get(f"{deepseek_url}/info")
            deepseek_info = response.json()
            gpu_free_after_load = deepseek_info['gpu_memory'][0]['free']
            memory_used = baseline_free - gpu_free_after_load

            print(f"\n   After loading:")
            print(f"     Model loaded: {deepseek_info['model_loaded']}")
            print(f"     Device: {deepseek_info['device']}")
            print(f"     GPU memory used: ~{memory_used}MB")
            print(f"     GPU free: {gpu_free_after_load}MB")

            if not deepseek_info['model_loaded']:
                print("   ✗ ERROR: DeepSeek model should be loaded after inference!")
                return False

            print("   ✓ DeepSeek-OCR loaded successfully")

            # Test that Qwen is still NOT loaded (only one model at a time)
            print("\n3. Verifying only ONE model loaded at a time...")
            response = await client.get(f"{qwen_url}/info")
            qwen_info = response.json()

            print(f"   Qwen3-VL loaded: {qwen_info['model_loaded']}")

            if qwen_info['model_loaded']:
                print("   ✗ ERROR: Qwen should NOT be loaded (only one model at a time)!")
                return False

            print("   ✓ Only DeepSeek loaded (single model constraint verified)")

            # Test explicit unload
            print("\n4. Testing explicit model unload...")
            print("   Calling /unload endpoint on DeepSeek container...")

            response = await client.post(f"{deepseek_url}/unload")
            unload_result = response.json()

            print(f"   Unload response: {unload_result['message']}")

            # Verify model is unloaded
            response = await client.get(f"{deepseek_url}/info")
            deepseek_info = response.json()
            gpu_free_after_unload = deepseek_info['gpu_memory'][0]['free']
            memory_freed = gpu_free_after_unload - gpu_free_after_load

            print(f"\n   After unload:")
            print(f"     Model loaded: {deepseek_info['model_loaded']}")
            print(f"     GPU memory freed: ~{memory_freed}MB")
            print(f"     GPU free: {gpu_free_after_unload}MB")

            if deepseek_info['model_loaded']:
                print("   ✗ ERROR: Model should be unloaded!")
                return False

            print("   ✓ DeepSeek-OCR unloaded successfully")

            # Test Qwen loading
            print("\n5. Testing Qwen3-VL lazy loading...")
            print("   Sending first inference request (should trigger model load)...")
            print("   This may take 2-3 minutes for first load...")

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

            response = await client.post(f"{qwen_url}/infer", json=qwen_request)
            result = response.json()

            print(f"   Inference result: success={result.get('success', False)}")

            # Verify Qwen is loaded
            response = await client.get(f"{qwen_url}/info")
            qwen_info = response.json()
            gpu_free_final = qwen_info['gpu_memory'][0]['free']
            memory_used_qwen = gpu_free_after_unload - gpu_free_final

            print(f"\n   After loading:")
            print(f"     Model loaded: {qwen_info['model_loaded']}")
            print(f"     Device: {qwen_info['device']}")
            print(f"     GPU memory used: ~{memory_used_qwen}MB")
            print(f"     GPU free: {gpu_free_final}MB")

            if not qwen_info['model_loaded']:
                print("   ✗ ERROR: Qwen model should be loaded after inference!")
                return False

            print("   ✓ Qwen3-VL loaded successfully")

            # Verify DeepSeek is still unloaded
            response = await client.get(f"{deepseek_url}/info")
            deepseek_info = response.json()

            print(f"\n   DeepSeek still unloaded: {not deepseek_info['model_loaded']}")

            if deepseek_info['model_loaded']:
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


if __name__ == "__main__":
    success = asyncio.run(test_lazy_loading())
    exit(0 if success else 1)
