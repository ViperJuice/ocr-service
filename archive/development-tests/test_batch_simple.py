"""Simple batch test with single image and longer timeout"""

import asyncio
import httpx
import base64
import json
from pathlib import Path

async def test_batch():
    image_path = Path("/home/jenner/code/ocr-service/tests/api/fixtures/sample.png")

    with open(image_path, 'rb') as f:
        image_bytes = f.read()
    b64_string = base64.b64encode(image_bytes).decode('utf-8')

    deepseek_url = "http://localhost:8001"

    batch_request = {
        "items": [
            {
                "image_base64": b64_string,
                "prompt": "Extract all text."
            }
        ],
        "auto_unload": False
    }

    print("Testing /batch_infer endpoint...")
    async with httpx.AsyncClient(timeout=600.0) as client:
        response = await client.post(f"{deepseek_url}/batch_infer", json=batch_request)
        result = response.json()
        print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(test_batch())
