"""Concurrent operations tests."""
import pytest
import asyncio


@pytest.mark.integration
class TestConcurrentUploads:
    """Test multiple simultaneous uploads."""

    @pytest.mark.asyncio
    async def test_concurrent_uploads_success(self, test_client, sample_pdf_path):
        """Scenario: Upload 5 files simultaneously."""
        # Arrange
        async def upload_file(filename):
            with open(sample_pdf_path, 'rb') as f:
                response = await test_client.post(
                    "/api/v1/process/upload",
                    files={"file": (filename, f, "application/pdf")}
                )
            return response

        # Act - Upload 5 files concurrently
        tasks = [upload_file(f"test{i}.pdf") for i in range(5)]
        responses = await asyncio.gather(*tasks)

        # Assert
        file_ids = set()
        for response in responses:
            assert response.status_code == 201
            file_id = response.json()["file_id"]
            file_ids.add(file_id)

        # All file_ids should be unique
        assert len(file_ids) == 5


@pytest.mark.integration
class TestConcurrentJobs:
    """Test multiple simultaneous jobs."""

    @pytest.mark.asyncio
    async def test_multiple_jobs_same_file(self, test_client, sample_pdf_path):
        """Scenario: Submit multiple jobs for same file."""
        # Arrange - Upload file
        with open(sample_pdf_path, 'rb') as f:
            upload_response = await test_client.post(
                "/api/v1/process/upload",
                files={"file": ("test.pdf", f, "application/pdf")}
            )
        file_id = upload_response.json()["file_id"]

        # Act - Submit 3 jobs for same file
        async def submit_job():
            return await test_client.post(
                "/api/v1/process/jobs",
                json={"file_id": file_id, "output_format": "markdown"}
            )

        tasks = [submit_job() for _ in range(3)]
        responses = await asyncio.gather(*tasks)

        # Assert
        job_ids = set()
        for response in responses:
            assert response.status_code == 202
            job_id = response.json()["job_id"]
            job_ids.add(job_id)

        # All job_ids should be unique
        assert len(job_ids) == 3
