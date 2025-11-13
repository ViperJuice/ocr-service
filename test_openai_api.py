"""
Test OpenAI-Compatible API Endpoints

Verifies that:
1. /v1/models endpoint works for both containers
2. /v1/chat/completions endpoint works (non-streaming)
3. /v1/chat/completions endpoint works with streaming
4. OpenAI message format is correctly converted
"""

import asyncio
import httpx
import base64
from PIL import Image
import io


def create_test_image() -> str:
    """Create a simple test image and return base64-encoded data URL"""
    # Create a white image with some basic content
    img = Image.new('RGB', (400, 100), color='white')

    # Convert to base64
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    image_bytes = buffer.getvalue()
    b64_string = base64.b64encode(image_bytes).decode('utf-8')

    # Return as data URL
    return f"data:image/png;base64,{b64_string}"


async def test_openai_api():
    """Test OpenAI-compatible API endpoints"""

    print("=" * 80)
    print("OPENAI-COMPATIBLE API TEST")
    print("=" * 80)

    qwen_url = "http://localhost:8002"
    deepseek_url = "http://localhost:8001"

    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            # Test 1: List models endpoints
            print("\n1. Testing /v1/models endpoints...")

            # Qwen models
            response = await client.get(f"{qwen_url}/v1/models")
            qwen_models = response.json()
            print(f"\n   Qwen3-VL models:")
            print(f"     {qwen_models['data'][0]['id']}")

            # DeepSeek models
            response = await client.get(f"{deepseek_url}/v1/models")
            deepseek_models = response.json()
            print(f"\n   DeepSeek-OCR models:")
            print(f"     {deepseek_models['data'][0]['id']}")

            print("\n   ✓ Models endpoints working")

            # Test 2: Non-streaming chat completions (Qwen)
            print("\n2. Testing non-streaming chat completions (Qwen)...")

            image_url = create_test_image()

            qwen_request = {
                "model": "Qwen/Qwen3-VL-8B-Instruct",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this image briefly."},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ]
                }],
                "max_tokens": 100,
                "temperature": 0.0,
                "stream": False
            }

            print("   Sending request to Qwen...")
            response = await client.post(f"{qwen_url}/v1/chat/completions", json=qwen_request)
            result = response.json()

            print(f"   Response ID: {result['id']}")
            print(f"   Model: {result['model']}")
            print(f"   Content length: {len(result['choices'][0]['message']['content'])} chars")
            print(f"   Finish reason: {result['choices'][0]['finish_reason']}")

            print("\n   ✓ Non-streaming Qwen chat completion working")

            # Test 3: Non-streaming chat completions (DeepSeek)
            print("\n3. Testing non-streaming chat completions (DeepSeek)...")

            deepseek_request = {
                "model": "deepseek-ai/DeepSeek-OCR",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract any text from this image."},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ]
                }],
                "max_tokens": 100,
                "temperature": 0.0,
                "stream": False
            }

            print("   Sending request to DeepSeek...")
            response = await client.post(f"{deepseek_url}/v1/chat/completions", json=deepseek_request)
            result = response.json()

            print(f"   Response ID: {result['id']}")
            print(f"   Model: {result['model']}")
            print(f"   Content length: {len(result['choices'][0]['message']['content'])} chars")
            print(f"   Finish reason: {result['choices'][0]['finish_reason']}")

            print("\n   ✓ Non-streaming DeepSeek chat completion working")

            # Test 4: Streaming chat completions (Qwen)
            print("\n4. Testing streaming chat completions (Qwen)...")

            qwen_stream_request = {
                **qwen_request,
                "stream": True
            }

            print("   Sending streaming request to Qwen...")
            chunk_count = 0
            total_content = ""

            async with client.stream(
                "POST",
                f"{qwen_url}/v1/chat/completions",
                json=qwen_stream_request,
                timeout=300.0
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break

                        import json
                        try:
                            chunk = json.loads(data)
                            if chunk['choices'][0].get('delta', {}).get('content'):
                                content = chunk['choices'][0]['delta']['content']
                                total_content += content
                                chunk_count += 1
                        except json.JSONDecodeError:
                            continue

            print(f"   Received {chunk_count} chunks")
            print(f"   Total content length: {len(total_content)} chars")

            print("\n   ✓ Streaming Qwen chat completion working")

            # Summary
            print("\n" + "=" * 80)
            print("✓ ALL OPENAI-COMPATIBLE API TESTS PASSED!")
            print("=" * 80)
            print(f"\nFeatures verified:")
            print(f"  ✓ /v1/models endpoint (both containers)")
            print(f"  ✓ Non-streaming chat completions (Qwen)")
            print(f"  ✓ Non-streaming chat completions (DeepSeek)")
            print(f"  ✓ Streaming chat completions (Qwen)")
            print(f"  ✓ OpenAI message format conversion")
            print(f"  ✓ Data URL image format support")

            return True

        except Exception as e:
            print(f"\n✗ Test failed: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    success = asyncio.run(test_openai_api())
    exit(0 if success else 1)
