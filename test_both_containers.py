"""Test both DeepSeek and Qwen containers"""

import asyncio
import httpx
import base64
import json
from pathlib import Path

async def test_both_containers():
    image_path = Path("/home/jenner/code/ocr-service/tests/api/fixtures/sample.png")

    with open(image_path, 'rb') as f:
        image_bytes = f.read()
    b64_string = base64.b64encode(image_bytes).decode('utf-8')

    print("="*70)
    print("TESTING BOTH OCR CONTAINERS")
    print("="*70)

    async with httpx.AsyncClient(timeout=300.0) as client:
        # Test 1: DeepSeek Container
        print("\n" + "="*70)
        print("TEST 1: DeepSeek-OCR Container (Port 8001)")
        print("="*70)

        deepseek_request = {
            "image_base64": b64_string,
            "prompt": "Extract all text from this image.",
            "base_size": 1024,
            "image_size": 640,
            "crop_mode": True
        }

        print("\nRequest format: image_base64 + prompt + parameters")
        print("Sending request to http://localhost:8001/infer...")

        try:
            response = await client.post(
                "http://localhost:8001/infer",
                json=deepseek_request
            )
            result = response.json()
            print("\n✅ DeepSeek Response:")
            print(json.dumps(result, indent=2))
        except Exception as e:
            print(f"\n❌ DeepSeek Error: {e}")

        # Test 2: Qwen Container
        print("\n" + "="*70)
        print("TEST 2: Qwen3-VL Container (Port 8002)")
        print("="*70)

        qwen_request = {
            "image_base64": b64_string,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract all text from this image."}
                    ]
                }
            ]
        }

        print("\nRequest format: image_base64 + messages (chat format)")
        print("Sending request to http://localhost:8002/infer...")

        try:
            response = await client.post(
                "http://localhost:8002/infer",
                json=qwen_request
            )
            result = response.json()
            print("\n✅ Qwen Response:")
            print(json.dumps(result, indent=2))
        except Exception as e:
            print(f"\n❌ Qwen Error: {e}")

        # Test 3: OpenAI-Compatible Endpoints
        print("\n" + "="*70)
        print("TEST 3: OpenAI-Compatible Endpoints")
        print("="*70)

        openai_request = {
            "model": "deepseek-ai/DeepSeek-OCR",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract all text."},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_string}"}}
                    ]
                }
            ]
        }

        print("\n3a. DeepSeek OpenAI endpoint...")
        try:
            response = await client.post(
                "http://localhost:8001/v1/chat/completions",
                json=openai_request
            )
            result = response.json()
            print("✅ DeepSeek OpenAI Response:")
            print(f"  Message: {result['choices'][0]['message']['content']}")
        except Exception as e:
            print(f"❌ Error: {e}")

        print("\n3b. Qwen OpenAI endpoint...")
        try:
            response = await client.post(
                "http://localhost:8002/v1/chat/completions",
                json=openai_request
            )
            result = response.json()
            print("✅ Qwen OpenAI Response:")
            print(f"  Message: {result['choices'][0]['message']['content']}")
        except Exception as e:
            print(f"❌ Error: {e}")

    print("\n" + "="*70)
    print("ALL TESTS COMPLETE")
    print("="*70)

if __name__ == "__main__":
    asyncio.run(test_both_containers())
