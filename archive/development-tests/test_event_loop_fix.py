"""
Simple test to verify the event loop fix works.

This tests that we can submit a job and it completes without "Event loop is closed" error.
"""
import asyncio
import httpx
from pathlib import Path

BACKEND_URL = "http://localhost:8000"
PDF_PATH = Path("/home/jenner/code/ocr-service/tests/api/fixtures/sample.pdf")


async def test_job_submission():
    """Test that a job can be submitted and doesn't fail with event loop error."""
    print("\n" + "="*60)
    print("EVENT LOOP FIX TEST")
    print("="*60)

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Step 1: Upload file
        print("\n[1/3] Uploading file...")
        with open(PDF_PATH, "rb") as f:
            files = {"file": (PDF_PATH.name, f, "application/pdf")}
            response = await client.post(f"{BACKEND_URL}/api/v1/process/upload", files=files)
            response.raise_for_status()
            upload_result = response.json()
            file_id = upload_result["file_id"]
            print(f"✓ File uploaded: {file_id}")

        # Step 2: Submit job with page limit
        print("\n[2/3] Submitting job (page 1 only)...")
        job_request = {
            "file_id": file_id,
            "model": "deepseek-ocr",
            "output_format": "markdown",
            "processing_options": {
                "start_page": 1,
                "end_page": 1
            }
        }
        response = await client.post(f"{BACKEND_URL}/api/v1/process/jobs", json=job_request)
        response.raise_for_status()
        job = response.json()
        job_id = job["job_id"]
        print(f"✓ Job submitted: {job_id}")

        # Step 3: Poll job status
        print("\n[3/3] Monitoring job status...")
        for i in range(60):  # 60 seconds max
            await asyncio.sleep(1)
            response = await client.get(f"{BACKEND_URL}/api/v1/process/jobs/{job_id}")
            response.raise_for_status()
            job_status = response.json()

            status = job_status["status"]
            progress = job_status.get("progress_pct", 0)

            print(f"  [{i+1}s] Status: {status}, Progress: {progress:.1f}%", end="\r")

            if status == "completed":
                print(f"\n✓ Job completed successfully!")
                print(f"  No 'Event loop is closed' error occurred")
                return True

            if status == "failed":
                error = job_status.get("error", "Unknown error")
                print(f"\n✗ Job failed: {error}")

                # Check if it's the event loop error
                if "Event loop is closed" in error:
                    print("  ERROR: Event loop bug still present!")
                    return False
                else:
                    print("  ERROR: Different error (not event loop related)")
                    return False

        print(f"\n✗ Timeout after 60 seconds")
        return False


async def main():
    try:
        success = await test_job_submission()

        print("\n" + "="*60)
        if success:
            print("✓ TEST PASSED")
            print("  Event loop fix is working correctly!")
        else:
            print("✗ TEST FAILED")
            print("  Event loop bug may still be present")
        print("="*60 + "\n")

    except Exception as e:
        print(f"\n✗ Test error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
