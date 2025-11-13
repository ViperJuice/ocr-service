"""Test all DeepSeek container endpoints with official parameters"""

import asyncio
import httpx
import base64
import json
from pathlib import Path

async def test_all_endpoints():
    image_path = Path("/home/jenner/code/ocr-service/tests/api/fixtures/sample.png")

    with open(image_path, 'rb') as f:
        image_bytes = f.read()
    b64_string = base64.b64encode(image_bytes).decode('utf-8')

    deepseek_url = "http://localhost:8001"

    # Wait for container to be ready
    print("Waiting for container to be ready...")
    await asyncio.sleep(20)

    async with httpx.AsyncClient(timeout=300.0) as client:
        # Test 1: /infer endpoint
        print("\n" + "="*60)
        print("TEST 1: /infer endpoint")
        print("="*60)

        infer_request = {
            "image_base64": b64_string,
            "prompt": "Extract all text from this image.",
            "base_size": 1024,
            "image_size": 640,  # Official parameter
            "crop_mode": True
        }

        response = await client.post(f"{deepseek_url}/infer", json=infer_request)
        result = response.json()
        print(json.dumps(result, indent=2))

        # Test 2: /batch_infer endpoint
        print("\n" + "="*60)
        print("TEST 2: /batch_infer endpoint")
        print("="*60)

        batch_request = {
            "items": [
                {
                    "image_base64": b64_string,
                    "prompt": "Extract text from image 1."
                },
                {
                    "image_base64": b64_string,
                    "prompt": "What text is in this image?"
                }
            ],
            "base_size": 1024,
            "image_size": 640,  # Official parameter
            "crop_mode": True,
            "auto_unload": False
        }

        response = await client.post(f"{deepseek_url}/batch_infer", json=batch_request)
        result = response.json()
        print(json.dumps(result, indent=2))

        # Test 3: /v1/chat/completions endpoint (OpenAI-compatible)
        print("\n" + "="*60)
        print("TEST 3: /v1/chat/completions endpoint (OpenAI-compatible)")
        print("="*60)

        openai_request = {
            "model": "deepseek-ai/DeepSeek-OCR",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Please extract all text from this image."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{b64_string}"
                            }
                        }
                    ]
                }
            ]
        }

        response = await client.post(f"{deepseek_url}/v1/chat/completions", json=openai_request)
        result = response.json()
        print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(test_all_endpoints())
