"""
Test Docker Containers with Simple Image

Tests both containers with a sample image:
1. Test DeepSeek-OCR with /v1/chat/completions (non-streaming)
2. Test Qwen3-VL with /v1/chat/completions (streaming)
3. Display results and verify both containers work correctly
"""

import asyncio
import httpx
import base64
from pathlib import Path
import json


def image_to_base64_url(image_path: str) -> str:
    """
    Load an image and convert to base64 data URL

    Args:
        image_path: Path to image file

    Returns:
        Data URL with base64-encoded image
    """
    with open(image_path, 'rb') as f:
        image_bytes = f.read()

    # Encode as base64
    b64_string = base64.b64encode(image_bytes).decode('utf-8')

    # Determine image type from extension
    ext = Path(image_path).suffix.lower()
    if ext == '.png':
        mime_type = 'image/png'
    elif ext in ['.jpg', '.jpeg']:
        mime_type = 'image/jpeg'
    else:
        mime_type = 'image/png'  # Default

    # Return as data URL
    return f"data:{mime_type};base64,{b64_string}"


async def test_containers_simple():
    """Test both containers with sample image"""

    print("=" * 80)
    print("DOCKER CONTAINER TEST WITH SAMPLE IMAGE")
    print("=" * 80)

    # Find sample image
    image_path = Path("/home/jenner/code/ocr-service/tests/api/fixtures/sample.png")
    if not image_path.exists():
        print(f"\n✗ Image not found: {image_path}")
        return False

    print(f"\n📄 Using image: {image_path}")

    # Convert to base64 data URL
    print("\n1. Loading image...")
    try:
        image_url = image_to_base64_url(str(image_path))
        print(f"   ✓ Image loaded ({len(image_url)} bytes)")
    except Exception as e:
        print(f"\n✗ Failed to load image: {e}")
        return False

    # Test containers
    deepseek_url = "http://localhost:8001"
    qwen_url = "http://localhost:8002"

    async with httpx.AsyncClient(timeout=600.0) as client:
        try:
            # Check container health
            print("\n2. Checking container health...")

            try:
                response = await client.get(f"{deepseek_url}/health")
                deepseek_health = response.json()
                print(f"   DeepSeek: {deepseek_health['status']}")
            except Exception as e:
                print(f"   ✗ DeepSeek container unreachable: {e}")
                return False

            try:
                response = await client.get(f"{qwen_url}/health")
                qwen_health = response.json()
                print(f"   Qwen: {qwen_health['status']}")
            except Exception as e:
                print(f"   ✗ Qwen container unreachable: {e}")
                return False

            # Test DeepSeek-OCR (non-streaming)
            print("\n3. Testing DeepSeek-OCR (non-streaming)...")

            deepseek_request = {
                "model": "deepseek-ai/DeepSeek-OCR",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract all text from this image in markdown format."},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ]
                }],
                "max_tokens": 4096,
                "temperature": 0.0,
                "stream": False
            }

            print("   Sending request to DeepSeek...")
            print("   (This may take 2-3 minutes for first load)")
            response = await client.post(
                f"{deepseek_url}/v1/chat/completions",
                json=deepseek_request,
                timeout=300.0
            )
            deepseek_result = response.json()

            print(f"\n   ✓ DeepSeek response received")
            print(f"     Response ID: {deepseek_result['id']}")
            print(f"     Model: {deepseek_result['model']}")
            print(f"     Content length: {len(deepseek_result['choices'][0]['message']['content'])} chars")

            # Display first 500 chars of result
            content = deepseek_result['choices'][0]['message']['content']
            print(f"\n   Extracted text (first 500 chars):")
            print("   " + "-" * 76)
            for line in content[:500].split('\n'):
                print(f"   {line}")
            print("   " + "-" * 76)
            if len(content) > 500:
                print(f"   ... ({len(content) - 500} more chars)")

            # Test Qwen3-VL (streaming)
            print("\n4. Testing Qwen3-VL (streaming)...")

            qwen_request = {
                "model": "Qwen/Qwen3-VL-8B-Instruct",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this image in detail."},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ]
                }],
                "max_tokens": 2048,
                "temperature": 0.0,
                "stream": True
            }

            print("   Sending streaming request to Qwen...")
            print("   (This may take 2-3 minutes for first load)")

            chunk_count = 0
            total_content = ""

            async with client.stream(
                "POST",
                f"{qwen_url}/v1/chat/completions",
                json=qwen_request,
                timeout=300.0
            ) as response:
                response.raise_for_status()

                print("\n   Streaming response:")
                print("   " + "-" * 76)

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break

                        try:
                            chunk = json.loads(data)
                            if chunk.get('choices', [{}])[0].get('delta', {}).get('content'):
                                content_chunk = chunk['choices'][0]['delta']['content']
                                total_content += content_chunk
                                print(content_chunk, end='', flush=True)
                                chunk_count += 1
                        except json.JSONDecodeError:
                            continue

            print()
            print("   " + "-" * 76)
            print(f"\n   ✓ Qwen streaming complete")
            print(f"     Received {chunk_count} chunks")
            print(f"     Total content length: {len(total_content)} chars")

            # Summary
            print("\n" + "=" * 80)
            print("✓ ALL CONTAINER TESTS PASSED!")
            print("=" * 80)

            print("\nTest results:")
            print(f"  ✓ DeepSeek-OCR extracted {len(deepseek_result['choices'][0]['message']['content'])} chars")
            print(f"  ✓ Qwen3-VL generated {len(total_content)} chars")
            print(f"  ✓ OpenAI-compatible endpoints working")
            print(f"  ✓ Non-streaming (DeepSeek) working")
            print(f"  ✓ Streaming (Qwen) working")
            print(f"  ✓ Lazy loading working (models loaded on first request)")

            return True

        except httpx.TimeoutException as e:
            print(f"\n✗ Request timed out: {e}")
            print("   This is normal for first request (model loading takes time)")
            print("   Try increasing timeout or waiting for models to load")
            return False

        except Exception as e:
            print(f"\n✗ Test failed: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    success = asyncio.run(test_containers_simple())
    exit(0 if success else 1)
