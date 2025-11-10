#!/usr/bin/env python3
"""Test script for batch processing functionality."""
import asyncio
import httpx
import json
import sys
from pathlib import Path

API_BASE = "http://localhost:8000"
TEST_PDF = Path("ai-docs/deepseek-ocr/DeepSeek_OCR_paper.pdf")


async def test_directory_upload():
    """Test directory upload endpoint."""
    print("=" * 60)
    print("TEST 1: Directory Upload")
    print("=" * 60)

    if not TEST_PDF.exists():
        print(f"❌ Error: Test PDF not found at {TEST_PDF}")
        return None

    async with httpx.AsyncClient(timeout=120.0) as client:
        # Upload directory with a single PDF
        files = [
            ("files", (TEST_PDF.name, open(TEST_PDF, "rb"), "application/pdf"))
        ]
        data = {"directory_name": "test_batch_directory"}

        print(f"\n📤 Uploading directory with {TEST_PDF.name}...")

        try:
            response = await client.post(
                f"{API_BASE}/api/v1/files/directories/upload",
                files=files,
                data=data
            )

            if response.status_code == 200:
                result = response.json()
                print(f"✅ Directory uploaded successfully!")
                print(f"   Directory ID: {result['directory_id']}")
                print(f"   Name: {result['name']}")
                print(f"   File count: {result['file_count']}")
                print(f"   Total size: {result['total_size']} bytes")
                return result['directory_id']
            else:
                print(f"❌ Upload failed: {response.status_code}")
                print(f"   Response: {response.text}")
                return None

        except Exception as e:
            import traceback
            print(f"❌ Error during upload: {e}")
            print(f"   Traceback:")
            traceback.print_exc()
            return None


async def test_batch_submission(directory_id: str):
    """Test batch job submission."""
    print("\n" + "=" * 60)
    print("TEST 2: Batch Job Submission")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=120.0) as client:
        payload = {
            "directory_id": directory_id,
            "model": "deepseek-ocr",
            "prompt_type": "default",
            "output_format": "markdown",
            "processing_options": {
                "enable_chunking": False,
                "max_pages_per_chunk": 10
            }
        }

        print(f"\n🚀 Submitting batch job for directory: {directory_id}")
        print(f"   Model: {payload['model']}")
        print(f"   Output format: {payload['output_format']}")

        try:
            response = await client.post(
                f"{API_BASE}/api/v1/batch/process",
                json=payload
            )

            if response.status_code == 200:
                result = response.json()
                print(f"✅ Batch job submitted successfully!")
                print(f"   Batch Job ID: {result['batch_job_id']}")
                print(f"   Total documents: {result['total_documents']}")
                print(f"   Status: {result['status']}")
                return result['batch_job_id']
            else:
                print(f"❌ Batch submission failed: {response.status_code}")
                print(f"   Response: {response.text}")
                return None

        except Exception as e:
            print(f"❌ Error during batch submission: {e}")
            return None


async def test_progress_stream(batch_job_id: str):
    """Test SSE progress streaming."""
    print("\n" + "=" * 60)
    print("TEST 3: Progress Stream (SSE)")
    print("=" * 60)

    print(f"\n📡 Connecting to progress stream for batch: {batch_job_id}...")

    async with httpx.AsyncClient(timeout=None) as client:
        try:
            async with client.stream(
                "GET",
                f"{API_BASE}/api/v1/batch/progress/stream"
            ) as response:
                if response.status_code != 200:
                    print(f"❌ Failed to connect to stream: {response.status_code}")
                    return

                print("✅ Connected to progress stream!")
                print("\n📊 Progress updates:")
                print("-" * 60)

                event_count = 0
                completion_received = False

                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        event_type = line.split(":", 1)[1].strip()
                    elif line.startswith("data:"):
                        event_count += 1
                        data = json.loads(line.split(":", 1)[1].strip())

                        if event_type == "connected":
                            print(f"   [CONNECTED] Connection ID: {data.get('connection_id')}")

                        elif event_type == "batch_progress":
                            print(f"   [BATCH] Progress: {data.get('overall_progress_pct', 0):.1f}% | "
                                  f"Docs: {data.get('documents_completed', 0)}/{data.get('total_documents', 0)}")

                        elif event_type == "document_progress":
                            print(f"   [DOC] {data.get('filename', 'unknown')} - "
                                  f"{data.get('progress_pct', 0):.1f}% | "
                                  f"Page: {data.get('current_page', 0)}/{data.get('total_pages', 0)} | "
                                  f"Stage: {data.get('stage', 'unknown')}")

                        elif event_type == "completion":
                            print(f"   [COMPLETE] Batch finished!")
                            if data.get('batch_stats'):
                                stats = data['batch_stats']
                                print(f"      Total: {stats.get('total_documents', 0)}")
                                print(f"      Completed: {stats.get('documents_completed', 0)}")
                                print(f"      Failed: {stats.get('documents_failed', 0)}")
                                print(f"      Time: {stats.get('overall_processing_time_seconds', 0):.2f}s")
                            completion_received = True
                            break

                        elif event_type == "error":
                            print(f"   [ERROR] {data.get('error_message', 'Unknown error')}")
                            break

                print("-" * 60)
                print(f"\n📈 Total events received: {event_count}")

                if completion_received:
                    print("✅ Batch completed successfully!")
                    return True
                else:
                    print("⚠️  Stream ended without completion")
                    return False

        except Exception as e:
            print(f"❌ Error during streaming: {e}")
            return False


async def test_batch_status(batch_job_id: str):
    """Test batch status endpoint."""
    print("\n" + "=" * 60)
    print("TEST 4: Batch Status Check")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=120.0) as client:
        print(f"\n🔍 Checking batch status: {batch_job_id}")

        try:
            response = await client.get(
                f"{API_BASE}/api/v1/batch/{batch_job_id}/status"
            )

            if response.status_code == 200:
                result = response.json()
                print(f"✅ Batch status retrieved!")
                print(f"   Status: {result['status']}")
                print(f"   Progress: {result['overall_progress_pct']:.1f}%")
                print(f"   Completed: {result['documents_completed']}/{result['total_documents']}")
                return True
            else:
                print(f"❌ Status check failed: {response.status_code}")
                return False

        except Exception as e:
            print(f"❌ Error during status check: {e}")
            return False


async def test_batch_result(batch_job_id: str):
    """Test batch result endpoint."""
    print("\n" + "=" * 60)
    print("TEST 5: Batch Result Retrieval")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=120.0) as client:
        print(f"\n📥 Retrieving batch results: {batch_job_id}")

        try:
            response = await client.get(
                f"{API_BASE}/api/v1/batch/{batch_job_id}/result"
            )

            if response.status_code == 200:
                result = response.json()
                print(f"✅ Batch results retrieved!")
                print(f"   Total documents: {result['total_documents']}")
                print(f"   Completed: {result['documents_completed']}")
                print(f"   Processing time: {result['overall_processing_time_seconds']:.2f}s")

                for doc_result in result['results']:
                    print(f"\n   📄 {doc_result['filename']}")
                    print(f"      Status: {doc_result['status']}")
                    if doc_result['status'] == 'completed':
                        print(f"      Format: {doc_result['format']}")
                        print(f"      Pages: {doc_result['total_pages']}")
                        print(f"      Content length: {len(doc_result['content'])} chars")
                    elif doc_result['status'] == 'failed':
                        print(f"      Error: {doc_result.get('error', 'Unknown')}")

                return True
            else:
                print(f"❌ Result retrieval failed: {response.status_code}")
                print(f"   Response: {response.text}")
                return False

        except Exception as e:
            print(f"❌ Error during result retrieval: {e}")
            return False


async def main():
    """Run all tests."""
    print("\n🧪 BATCH PROCESSING TEST SUITE")
    print("=" * 60)

    # Test 1: Directory upload
    directory_id = await test_directory_upload()
    if not directory_id:
        print("\n❌ Test suite failed at directory upload")
        return 1

    # Test 2: Batch submission
    batch_job_id = await test_batch_submission(directory_id)
    if not batch_job_id:
        print("\n❌ Test suite failed at batch submission")
        return 1

    # Test 3: Progress streaming (waits for completion)
    stream_success = await test_progress_stream(batch_job_id)

    # Test 4: Status check
    await test_batch_status(batch_job_id)

    # Test 5: Result retrieval (only if completed)
    if stream_success:
        await test_batch_result(batch_job_id)

    print("\n" + "=" * 60)
    print("✅ TEST SUITE COMPLETED")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
        sys.exit(130)
