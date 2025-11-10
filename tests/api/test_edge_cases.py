"""Edge case tests."""
import pytest


@pytest.mark.api
class TestEdgeCaseRequests:
    """Test unusual API requests."""

    @pytest.mark.asyncio
    async def test_malformed_json(self, test_client):
        """Scenario: Invalid JSON in request body."""
        # Act
        response = await test_client.post(
            "/api/v1/process/jobs",
            data="not valid json",
            headers={"Content-Type": "application/json"}
        )

        # Assert
        assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_special_characters_in_filename(self, test_client, sample_pdf_path):
        """Scenario: Filename with special characters."""
        # Arrange
        special_filename = "test file (1) [special] 'chars'.pdf"

        # Act
        with open(sample_pdf_path, 'rb') as f:
            response = await test_client.post(
                "/api/v1/process/upload",
                files={"file": (special_filename, f, "application/pdf")}
            )

        # Assert - Should handle gracefully
        assert response.status_code == 201
        data = response.json()
        # Filename may be sanitized or preserved
        assert data["filename"] == special_filename

    @pytest.mark.asyncio
    async def test_duplicate_job_submission(self, test_client, sample_pdf_path):
        """Scenario: Submit same job twice rapidly."""
        # Arrange - Upload file
        with open(sample_pdf_path, 'rb') as f:
            upload_response = await test_client.post(
                "/api/v1/process/upload",
                files={"file": ("test.pdf", f, "application/pdf")}
            )
        file_id = upload_response.json()["file_id"]

        # Act - Submit twice
        response1 = await test_client.post(
            "/api/v1/process/jobs",
            json={"file_id": file_id, "output_format": "markdown"}
        )
        response2 = await test_client.post(
            "/api/v1/process/jobs",
            json={"file_id": file_id, "output_format": "markdown"}
        )

        # Assert - Both should succeed with different job IDs
        assert response1.status_code == 202
        assert response2.status_code == 202
        assert response1.json()["job_id"] != response2.json()["job_id"]


@pytest.mark.api
class TestStateTransitionEdgeCases:
    """Test invalid state transitions."""

    @pytest.mark.asyncio
    async def test_get_result_of_cancelled_job(self, test_client, sample_pdf_path):
        """Scenario: Get result of cancelled job."""
        # Arrange - Upload and submit job
        with open(sample_pdf_path, 'rb') as f:
            upload_response = await test_client.post(
                "/api/v1/process/upload",
                files={"file": ("test.pdf", f, "application/pdf")}
            )
        file_id = upload_response.json()["file_id"]

        submit_response = await test_client.post(
            "/api/v1/process/jobs",
            json={"file_id": file_id, "output_format": "markdown"}
        )
        job_id = submit_response.json()["job_id"]

        # Cancel the job
        cancel_response = await test_client.delete(f"/api/v1/process/jobs/{job_id}")

        # Act - Try to get result
        result_response = await test_client.get(f"/api/v1/process/jobs/{job_id}/result")

        # Assert - Should fail appropriately
        assert result_response.status_code in [400, 409]
