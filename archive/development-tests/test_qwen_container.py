"""Test Qwen-VL container inference"""

import asyncio
import httpx
import base64
import json
from pathlib import Path

async def test_qwen():
    image_path = Path("/home/jenner/code/ocr-service/tests/api/fixtures/sample.png")

    with open(image_path, 'rb') as f:
        image_bytes = f.read()
    b64_string = base64.b64encode(image_bytes).decode('utf-8')

    qwen_url = "http://localhost:8002"

    # Test /infer endpoint with messages format
    print("Testing Qwen /infer endpoint...")
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

    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(
            f"{qwen_url}/infer",
            json=qwen_request
        )
        result = response.json()

        print("Full response:")
        print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(test_qwen())
