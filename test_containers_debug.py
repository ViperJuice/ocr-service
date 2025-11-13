"""Quick debug test to see response format"""

import asyncio
import httpx
import base64
from pathlib import Path
import json


async def test_debug():
    image_path = Path("/home/jenner/code/ocr-service/tests/api/fixtures/sample.png")

    with open(image_path, 'rb') as f:
        image_bytes = f.read()
    b64_string = base64.b64encode(image_bytes).decode('utf-8')
    image_url = f"data:image/png;base64,{b64_string}"

    deepseek_url = "http://localhost:8001"

    deepseek_request = {
        "model": "deepseek-ai/DeepSeek-OCR",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": "Extract all text from this image."},
                {"type": "image_url", "image_url": {"url": image_url}}
            ]
        }],
        "max_tokens": 100,
        "temperature": 0.0,
        "stream": False
    }

    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(
            f"{deepseek_url}/v1/chat/completions",
            json=deepseek_request
        )
        result = response.json()

        print("Full response:")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(test_debug())
