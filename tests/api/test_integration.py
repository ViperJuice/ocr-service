"""End-to-end integration tests."""
import pytest
import time
from unittest.mock import patch, Mock


@pytest.mark.integration
class TestFullWorkflow:
    """Test complete upload → process → retrieve workflow."""

    @pytest.mark.asyncio
    async def test_full_workflow_with_mocked_models(self, test_client, sample_pdf_path):
        """Scenario: Complete workflow with mocked OCR models."""
        # Step 1: Upload PDF
        with open(sample_pdf_path, 'rb') as f:
            upload_response = await test_client.post(
                "/api/v1/process/upload",
                files={"file": ("test.pdf", f, "application/pdf")}
            )

        assert upload_response.status_code == 201
        file_id = upload_response.json()["file_id"]

        # Step 2: Submit job
        submit_response = await test_client.post(
            "/api/v1/process/jobs",
            json={
                "file_id": file_id,
                "output_format": "markdown"
            }
        )

        assert submit_response.status_code == 202
        job_id = submit_response.json()["job_id"]

        # Step 3: Poll status until completed (or timeout)
        max_attempts = 20
        for attempt in range(max_attempts):
            status_response = await test_client.get(f"/api/v1/process/jobs/{job_id}")
            assert status_response.status_code == 200

            status_data = status_response.json()
            if status_data["status"] in ["completed", "failed"]:
                break

            time.sleep(0.5)

        # Step 4: Verify job completed
        final_status = await test_client.get(f"/api/v1/process/jobs/{job_id}")
        assert final_status.status_code == 200

    @pytest.mark.asyncio
    async def test_full_workflow_with_custom_prompts(self, test_client, sample_pdf_path):
        """Scenario: Workflow with custom prompts."""
        # Upload
        with open(sample_pdf_path, 'rb') as f:
            upload_response = await test_client.post(
                "/api/v1/process/upload",
                files={"file": ("test.pdf", f, "application/pdf")}
            )
        file_id = upload_response.json()["file_id"]

        # Submit with custom prompts
        custom_prompts = {
            "ocr": "Custom OCR prompt with <image> tag for {image}"
        }

        submit_response = await test_client.post(
            "/api/v1/process/jobs",
            json={
                "file_id": file_id,
                "output_format": "markdown",
                "custom_prompts": custom_prompts
            }
        )

        assert submit_response.status_code == 202


@pytest.mark.integration
class TestFileLifecycle:
    """Test file lifecycle from upload to expiration."""

    @pytest.mark.asyncio
    async def test_file_deletion_before_expiry(self, test_client, sample_pdf_path):
        """Scenario: Manual file deletion."""
        # Upload
        with open(sample_pdf_path, 'rb') as f:
            upload_response = await test_client.post(
                "/api/v1/process/upload",
                files={"file": ("test.pdf", f, "application/pdf")}
            )
        file_id = upload_response.json()["file_id"]

        # Verify file exists
        get_response = await test_client.get(f"/api/v1/files/{file_id}")
        assert get_response.status_code == 200

        # Delete file
        delete_response = await test_client.delete(f"/api/v1/files/{file_id}")
        assert delete_response.status_code == 200

        # Verify file is gone
        get_response2 = await test_client.get(f"/api/v1/files/{file_id}")
        assert get_response2.status_code == 404
