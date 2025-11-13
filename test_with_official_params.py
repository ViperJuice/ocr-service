"""Test with official DeepSeek-OCR parameters"""

import asyncio
import httpx
import base64
from pathlib import Path


async def test_official_params():
    image_path = Path("/home/jenner/code/ocr-service/tests/api/fixtures/sample.png")

    with open(image_path, 'rb') as f:
        image_bytes = f.read()
    b64_string = base64.b64encode(image_bytes).decode('utf-8')

    deepseek_url = "http://localhost:8001"

    # Use official parameters from DeepSeek-OCR README
    deepseek_request = {
        "image_base64": b64_string,
        "prompt": "Extract all text from this image.",
        "base_size": 1024,  # Official
        "image_size": 640,  # Official (NOT 1024!)
        "crop_mode": True   # Official
    }

    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(
            f"{deepseek_url}/infer",
            json=deepseek_request
        )
        result = response.json()

        print("Full response:")
        import json
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(test_official_params())
