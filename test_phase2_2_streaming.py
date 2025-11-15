#!/usr/bin/env python3
"""
Test Phase 2.2: Verify merge page events include metadata (processing_time, total_pages)
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx


async def test_merge_streaming_metadata():
    """Verify merge page events include metadata"""

    print("=" * 80)
    print("Phase 2.2 Integration Test: Merge Page Metadata Streaming")
    print("=" * 80)
    print()

    base_url = "http://localhost:8000"

    # Check if test PDF exists
    test_pdf = Path("tests/api/fixtures/sample.pdf")
    if not test_pdf.exists():
        print(f"❌ Test PDF not found: {test_pdf}")
        print("   Please ensure the test PDF exists before running this test.")
        sys.exit(1)

    print(f"✓ Using test PDF: {test_pdf}")
    print()

    async with httpx.AsyncClient(timeout=300.0) as client:
        # Step 1: Upload file
        print("Step 1: Uploading PDF...")
        with open(test_pdf, "rb") as f:
            upload_response = await client.post(
                f"{base_url}/files/upload",
                files={"file": (test_pdf.name, f, "application/pdf")}
            )

        if upload_response.status_code != 200:
            print(f"❌ Upload failed: {upload_response.status_code}")
            print(upload_response.text)
            sys.exit(1)

        file_data = upload_response.json()
        file_id = file_data["file_id"]
        print(f"✓ File uploaded: {file_id}")
        print()

        # Step 2: Submit job
        print("Step 2: Submitting OCR job...")
        job_response = await client.post(
            f"{base_url}/jobs",
            json={
                "file_id": file_id,
                "processing_options": {
                    "staged_pipeline": True,
                    "start_page": 1,
                    "end_page": 3  # Process first 3 pages
                }
            }
        )

        if job_response.status_code != 200:
            print(f"❌ Job submission failed: {job_response.status_code}")
            print(job_response.text)
            sys.exit(1)

        job_data = job_response.json()
        job_id = job_data["job_id"]
        print(f"✓ Job submitted: {job_id}")
        print()

        # Step 3: Listen to SSE stream
        print("Step 3: Listening to SSE stream for merge_page_complete events...")
        print("-" * 80)

        merge_events = []

        async with client.stream("GET", f"{base_url}/results/stream") as response:
            if response.status_code != 200:
                print(f"❌ Stream connection failed: {response.status_code}")
                sys.exit(1)

            async for line in response.aiter_lines():
                if not line:
                    continue

                # Parse SSE format
                if line.startswith("data: "):
                    try:
                        event_data = json.loads(line[6:])  # Skip "data: " prefix
                        event_type = event_data.get("event")

                        # Print all events for debugging
                        print(f"[EVENT] {event_type}")

                        # Check for merge_page_complete events
                        if event_type == "merge_page_complete":
                            data = event_data.get("data", {})
                            merge_events.append(data)

                            print(f"  → Merge Page {data.get('page_num')}")
                            print(f"     • Text length: {len(data.get('text', ''))} chars")
                            print(f"     • Processing time: {data.get('processing_time', 'N/A')}s")
                            print(f"     • Total pages: {data.get('total_pages', 'N/A')}")
                            print(f"     • Timestamp: {data.get('timestamp', 'N/A')}")
                            print()

                        # Check for job completion
                        if event_type == "job_complete":
                            print("[EVENT] job_complete - Job finished!")
                            break

                    except json.JSONDecodeError as e:
                        print(f"⚠ Failed to parse event: {line}")
                        print(f"   Error: {e}")

        print("-" * 80)
        print()

        # Step 4: Validate results
        print("Step 4: Validating results...")
        print()

        if not merge_events:
            print("❌ FAIL: No merge_page_complete events received!")
            sys.exit(1)

        print(f"✓ Received {len(merge_events)} merge page events")
        print()

        # Validate each event has the required metadata
        all_valid = True
        for i, event in enumerate(merge_events, 1):
            print(f"Event {i} (Page {event.get('page_num')}):")

            # Check required fields
            has_processing_time = "processing_time" in event
            has_total_pages = "total_pages" in event
            has_text = "text" in event
            has_timestamp = "timestamp" in event

            # Validate values
            processing_time_valid = False
            total_pages_valid = False

            if has_processing_time:
                pt = event.get("processing_time")
                processing_time_valid = isinstance(pt, (int, float)) and pt > 0
                print(f"  ✓ processing_time: {pt}s (valid: {processing_time_valid})")
            else:
                print(f"  ❌ processing_time: MISSING")
                all_valid = False

            if has_total_pages:
                tp = event.get("total_pages")
                page_num = event.get("page_num")
                total_pages_valid = isinstance(tp, int) and tp >= page_num
                print(f"  ✓ total_pages: {tp} (valid: {total_pages_valid})")
            else:
                print(f"  ❌ total_pages: MISSING")
                all_valid = False

            if has_text:
                text_len = len(event.get("text", ""))
                print(f"  ✓ text: {text_len} chars")
            else:
                print(f"  ❌ text: MISSING")
                all_valid = False

            if has_timestamp:
                print(f"  ✓ timestamp: {event.get('timestamp')}")
            else:
                print(f"  ❌ timestamp: MISSING")
                all_valid = False

            # Overall validation
            event_valid = (
                has_processing_time and processing_time_valid and
                has_total_pages and total_pages_valid and
                has_text and has_timestamp
            )

            if not event_valid:
                all_valid = False
                print(f"  ❌ Event {i} validation FAILED")
            else:
                print(f"  ✓ Event {i} validation PASSED")

            print()

        # Final result
        print("=" * 80)
        if all_valid:
            print("✅ PHASE 2.2 TEST PASSED!")
            print("   All merge_page_complete events include processing_time and total_pages")
        else:
            print("❌ PHASE 2.2 TEST FAILED!")
            print("   Some events are missing required metadata")
            sys.exit(1)
        print("=" * 80)


if __name__ == "__main__":
    try:
        asyncio.run(test_merge_streaming_metadata())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
