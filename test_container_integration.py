"""
Comprehensive test script for container-mode integration.

Tests the complete flow: Frontend → Backend → Containers → Results
"""
import asyncio
import httpx
import base64
import json
from pathlib import Path
import time

BACKEND_URL = "http://localhost:8000"
DEEPSEEK_URL = "http://localhost:8001"
QWEN_URL = "http://localhost:8002"

async def test_container_health():
    """Test container health checks."""
    print("\n" + "="*60)
    print("TEST 1: Container Health Checks")
    print("="*60)

    async with httpx.AsyncClient() as client:
        # Test DeepSeek
        try:
            response = await client.get(f"{DEEPSEEK_URL}/health", timeout=5.0)
            deepseek_health = response.json()
            print(f"✓ DeepSeek container: {deepseek_health}")
        except Exception as e:
            print(f"✗ DeepSeek container unreachable: {e}")
            return False

        # Test Qwen
        try:
            response = await client.get(f"{QWEN_URL}/health", timeout=5.0)
            qwen_health = response.json()
            print(f"✓ Qwen container: {qwen_health}")
        except Exception as e:
            print(f"✗ Qwen container unreachable: {e}")
            return False

    return True

async def test_backend_health():
    """Test backend API health."""
    print("\n" + "="*60)
    print("TEST 2: Backend API Health")
    print("="*60)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BACKEND_URL}/health", timeout=5.0)
            health = response.json()
            print(f"✓ Backend API: {health}")
            return True
        except Exception as e:
            print(f"✗ Backend API unreachable: {e}")
            return False

async def test_file_upload():
    """Test file upload."""
    print("\n" + "="*60)
    print("TEST 3: File Upload")
    print("="*60)

    # Use existing test file
    test_file = Path("/home/jenner/code/ocr-service/tests/api/fixtures/sample.pdf")
    if not test_file.exists():
        print(f"✗ Test file not found: {test_file}")
        return None

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            with open(test_file, "rb") as f:
                files = {"file": (test_file.name, f, "application/pdf")}
                response = await client.post(
                    f"{BACKEND_URL}/api/v1/process/upload",
                    files=files
                )
                response.raise_for_status()
                upload_result = response.json()
                file_id = upload_result["file_id"]
                print(f"✓ File uploaded: {file_id}")
                print(f"  Filename: {upload_result['filename']}")
                print(f"  Pages: {upload_result.get('page_count', 'unknown')}")
                return file_id
        except Exception as e:
            print(f"✗ File upload failed: {e}")
            return None

async def test_job_submission(file_id: str):
    """Test job submission."""
    print("\n" + "="*60)
    print("TEST 4: Job Submission (Container Mode)")
    print("="*60)

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            job_request = {
                "file_id": file_id,
                "model": "deepseek-ocr",
                "output_format": "markdown",
                "processing_options": {
                    "dpi": 300,
                    "staged_pipeline": True,
                    "prefer_quality": True
                }
            }

            response = await client.post(
                f"{BACKEND_URL}/api/v1/process/jobs",
                json=job_request
            )
            response.raise_for_status()
            job = response.json()
            job_id = job["job_id"]
            print(f"✓ Job submitted: {job_id}")
            print(f"  Status: {job['status']}")
            print(f"  Monitor URL: {job['monitor_url']}")
            return job_id
        except Exception as e:
            print(f"✗ Job submission failed: {e}")
            return None

async def test_job_monitoring(job_id: str, timeout: int = 300):
    """Monitor job progress and completion."""
    print("\n" + "="*60)
    print("TEST 5: Job Monitoring")
    print("="*60)

    start_time = time.time()
    last_progress = -1

    async with httpx.AsyncClient(timeout=10.0) as client:
        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                print(f"✗ Job timed out after {timeout}s")
                return False

            try:
                response = await client.get(
                    f"{BACKEND_URL}/api/v1/process/jobs/{job_id}"
                )
                response.raise_for_status()
                status = response.json()

                progress = status.get("progress_pct", 0)
                current_status = status["status"]

                # Print progress updates
                if int(progress) != int(last_progress):
                    stage = status.get("current_stage", "unknown")
                    pages_done = status.get("pages_completed", 0)
                    total_pages = status.get("total_pages", "?")
                    print(f"  Progress: {progress:.1f}% | Stage: {stage} | Pages: {pages_done}/{total_pages}")
                    last_progress = progress

                # Check if complete
                if current_status == "completed":
                    print(f"✓ Job completed in {elapsed:.1f}s")
                    return True
                elif current_status == "failed":
                    error = status.get("error", "Unknown error")
                    print(f"✗ Job failed: {error}")
                    return False

                await asyncio.sleep(2)

            except Exception as e:
                print(f"✗ Error monitoring job: {e}")
                return False

async def test_result_download(job_id: str):
    """Test result download."""
    print("\n" + "="*60)
    print("TEST 6: Result Download")
    print("="*60)

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                f"{BACKEND_URL}/api/v1/process/jobs/{job_id}/result/download"
            )
            response.raise_for_status()

            # Get content
            content = response.text
            lines = content.split('\n')
            preview_lines = min(10, len(lines))

            print(f"✓ Result downloaded")
            print(f"  Total length: {len(content)} characters")
            print(f"  Total lines: {len(lines)}")
            print(f"\n  Preview (first {preview_lines} lines):")
            for i, line in enumerate(lines[:preview_lines], 1):
                print(f"    {i}: {line[:80]}")

            return True
        except Exception as e:
            print(f"✗ Result download failed: {e}")
            return False

async def test_system_metrics():
    """Test system metrics endpoint."""
    print("\n" + "="*60)
    print("TEST 7: System Metrics (Container Status)")
    print("="*60)

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                f"{BACKEND_URL}/api/monitoring/system/current"
            )
            response.raise_for_status()
            metrics = response.json()

            print("✓ System metrics retrieved:")
            print(f"  CPU: {metrics.get('cpu_percent', 0):.1f}%")
            print(f"  RAM: {metrics.get('memory_percent', 0):.1f}%")

            # Container status
            containers = metrics.get("containers", {})
            print("\n  Container Status:")
            for name, info in containers.items():
                status = info.get("status", "unknown")
                available = info.get("available", False)
                model = info.get("model", "N/A")
                gpus = info.get("gpu_ids", [])
                print(f"    {name}: {status} | Model: {model} | GPUs: {gpus} | Available: {available}")

            return True
        except Exception as e:
            print(f"✗ System metrics failed: {e}")
            return False

async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("CONTAINER INTEGRATION TEST SUITE")
    print("="*60)
    print("\nTesting: Frontend → Backend → Containers → Results\n")

    results = {}

    # Test 1: Container health
    results["container_health"] = await test_container_health()
    if not results["container_health"]:
        print("\n✗ FAILED: Containers not healthy. Ensure Docker containers are running:")
        print("  docker compose up -d")
        return

    # Test 2: Backend health
    results["backend_health"] = await test_backend_health()
    if not results["backend_health"]:
        print("\n✗ FAILED: Backend not healthy. Ensure backend is running:")
        print("  uv run uvicorn src.api.main:app --reload")
        return

    # Test 3: File upload
    file_id = await test_file_upload()
    if not file_id:
        print("\n✗ FAILED: File upload failed")
        return
    results["file_upload"] = True

    # Test 4: Job submission
    job_id = await test_job_submission(file_id)
    if not job_id:
        print("\n✗ FAILED: Job submission failed")
        return
    results["job_submission"] = True

    # Test 5: Job monitoring
    results["job_monitoring"] = await test_job_monitoring(job_id, timeout=300)
    if not results["job_monitoring"]:
        print("\n✗ FAILED: Job monitoring/completion failed")
        return

    # Test 6: Result download
    results["result_download"] = await test_result_download(job_id)

    # Test 7: System metrics
    results["system_metrics"] = await test_system_metrics()

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    all_passed = all(results.values())
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")

    print("\n" + "="*60)
    if all_passed:
        print("✓ ALL TESTS PASSED")
        print("Container integration is working correctly!")
    else:
        print("✗ SOME TESTS FAILED")
        print("Please review the errors above.")
    print("="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
