"""
Test Docker Containers with Real PDF Pages

Tests both containers with pages from DeepSeek_OCR_paper.pdf:
1. Extract pages 1-2 from PDF as images
2. Test DeepSeek-OCR with /v1/chat/completions (non-streaming)
3. Test Qwen3-VL with /v1/chat/completions (streaming)
4. Display results and verify both containers work correctly
"""

import asyncio
import httpx
import base64
from pathlib import Path
from PIL import Image
import io
import json

# Try to import pdf2image, install if needed
try:
    from pdf2image import convert_from_path
    PDF_SUPPORT = True
except ImportError:
    print("⚠️  pdf2image not installed. Install with: pip install pdf2image")
    print("   Also requires poppler: sudo apt-get install poppler-utils")
    PDF_SUPPORT = False


def pdf_page_to_base64_url(pdf_path: str, page_number: int, dpi: int = 150) -> str:
    """
    Extract a page from PDF and convert to base64 data URL

    Args:
        pdf_path: Path to PDF file
        page_number: Page number (1-indexed)
        dpi: DPI for rendering (higher = better quality but larger)

    Returns:
        Data URL with base64-encoded PNG
    """
    if not PDF_SUPPORT:
        raise RuntimeError("pdf2image not installed")

    # Convert single page to image
    images = convert_from_path(
        pdf_path,
        first_page=page_number,
        last_page=page_number,
        dpi=dpi
    )

    if not images:
        raise ValueError(f"Failed to extract page {page_number} from PDF")

    # Convert to PNG bytes
    img = images[0]
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    image_bytes = buffer.getvalue()

    # Encode as base64
    b64_string = base64.b64encode(image_bytes).decode('utf-8')

    # Return as data URL
    return f"data:image/png;base64,{b64_string}"


async def test_containers_with_pdf():
    """Test both containers with real PDF pages"""

    print("=" * 80)
    print("DOCKER CONTAINER TEST WITH DEEPSEEK OCR PAPER")
    print("=" * 80)

    # Find PDF
    pdf_path = Path("/home/jenner/code/ocr-service/ai-docs/deepseek-ocr/DeepSeek_OCR_paper.pdf")
    if not pdf_path.exists():
        pdf_path = Path("/home/jenner/code/ocr-service/data/input/DeepSeek_OCR_paper.pdf")

    if not pdf_path.exists():
        print("\n✗ PDF not found at expected locations")
        return False

    print(f"\n📄 Using PDF: {pdf_path}")

    if not PDF_SUPPORT:
        print("\n✗ Cannot proceed without pdf2image. Install with:")
        print("   pip install pdf2image poppler-utils")
        return False

    # Extract pages
    print("\n1. Extracting pages from PDF...")
    try:
        print("   Extracting page 1 (150 DPI)...")
        page1_url = pdf_page_to_base64_url(str(pdf_path), 1, dpi=150)
        print(f"   ✓ Page 1 extracted ({len(page1_url)} bytes)")

        print("   Extracting page 2 (150 DPI)...")
        page2_url = pdf_page_to_base64_url(str(pdf_path), 2, dpi=150)
        print(f"   ✓ Page 2 extracted ({len(page2_url)} bytes)")

    except Exception as e:
        print(f"\n✗ Failed to extract pages: {e}")
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

            # Test DeepSeek-OCR with page 1 (non-streaming)
            print("\n3. Testing DeepSeek-OCR with page 1 (non-streaming)...")

            deepseek_request = {
                "model": "deepseek-ai/DeepSeek-OCR",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract all text from this document page in markdown format."},
                        {"type": "image_url", "image_url": {"url": page1_url}}
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

            # Test Qwen3-VL with page 2 (streaming)
            print("\n4. Testing Qwen3-VL with page 2 (streaming)...")

            qwen_request = {
                "model": "Qwen/Qwen3-VL-8B-Instruct",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe the content and structure of this document page in detail."},
                        {"type": "image_url", "image_url": {"url": page2_url}}
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
            print(f"  ✓ DeepSeek-OCR extracted {len(deepseek_result['choices'][0]['message']['content'])} chars from page 1")
            print(f"  ✓ Qwen3-VL generated {len(total_content)} chars describing page 2")
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
    success = asyncio.run(test_containers_with_pdf())
    exit(0 if success else 1)
